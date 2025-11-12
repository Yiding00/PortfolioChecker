import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib as mpl
from pymongo import MongoClient
import bcrypt
from uuid import uuid4  # 用于生成唯一ID

# ========== 基础配置 ==========
# 中文字体设置
mpl.font_manager.fontManager.addfont('font/NotoSansSC-VariableFont_wght.ttf')
plt.rcParams['font.sans-serif']=['Noto Sans SC']
plt.rcParams['axes.unicode_minus']=False

# MongoDB 连接
@st.cache_resource
def init_connection():
    return MongoClient(st.secrets["mongo"]["conn_str"])

client = init_connection()
db = client["user_db"]
users_collection = db["users"]

# 默认目标比例配置（首次使用时的初始值）
DEFAULT_CATEGORIES = {
    "债券": {
        "ratio": 0.40,
        "subcategories": {
            "利率/国债": 0.20,
            "信用/信用": 0.20
        }
    },
    "股票": {
        "ratio": 0.40,
        "subcategories": {
            "内地/沪深": 0.10,
            "内地/科创": 0.10,
            "内地/红利": 0.10,
            "全球/美股": 0.10
        }
    },
    "商品": {
        "ratio": 0.10,
        "subcategories": {
            "黄金": 0.10
        }
    },
    "机动": {
        "ratio": 0.10,
        "subcategories": {
            "现金": 0.10
        }
    }
}

# ========== 初始化 session_state ==========
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username_input" not in st.session_state:
    st.session_state.username_input = ""
if "password_input" not in st.session_state:
    st.session_state.password_input = ""
if "current_username" not in st.session_state:
    st.session_state.current_username = ""
if "delete_confirm" not in st.session_state:
    st.session_state.delete_confirm = False
if "asset_to_delete" not in st.session_state:
    st.session_state.asset_to_delete = ""
if "edit_categories" not in st.session_state:  # 控制分类编辑状态
    st.session_state.edit_categories = False
if "temp_categories" not in st.session_state:  # 临时存储编辑中的分类数据
    st.session_state.temp_categories = None

# ========== 核心函数 ==========
def get_user_config_from_db():
    """从数据库读取用户配置，若无则使用默认值"""
    if not st.session_state.current_username:
        return {}, DEFAULT_CATEGORIES
    
    user = users_collection.find_one(
        {"username": st.session_state.current_username},
        {"assets_info": 1, "categories": 1, "_id": 0}
    )
    
    # 若无配置则使用默认值
    return (
        user.get("assets_info", {}) if user else {},
        user.get("categories", DEFAULT_CATEGORIES) if user else DEFAULT_CATEGORIES
    )

def flatten_categories(categories):
    """将嵌套的分类结构展平为目标比例字典"""
    target_ratio = {name: data["ratio"] for name, data in categories.items()}
    target_ratio_sub = {}
    for major_name, major_data in categories.items():
        for minor_name, minor_ratio in major_data["subcategories"].items():
            full_name = f"{major_name}-{minor_name}"
            target_ratio_sub[full_name] = minor_ratio
    return target_ratio, target_ratio_sub

def save_categories_to_db(categories):
    """保存分类配置到数据库"""
    try:
        # 验证大类比例总和
        total_major = sum([data["ratio"] for data in categories.values()])
        if not (0.99 <= total_major <= 1.01):
            st.error(f"大类比例总和必须为100%，当前为{total_major:.2%}")
            return False
        
        # 验证每个大类的小类比例总和等于大类比例
        for major_name, major_data in categories.items():
            total_minor = sum(major_data["subcategories"].values())
            if not (0.99 * major_data["ratio"] <= total_minor <= 1.01 * major_data["ratio"]):
                st.error(
                    f"「{major_name}」的小类比例总和必须等于大类比例({major_data['ratio']:.0%})，"
                    f"当前为{total_minor:.0%}"
                )
                return False
        
        # 保存到数据库
        users_collection.update_one(
            {"username": st.session_state.current_username},
            {"$set": {"categories": categories}}
        )
        st.success("分类配置保存成功！")
        return True
    except Exception as e:
        st.error(f"保存失败：{str(e)}")
        return False

def check_password():
    """验证密码并设置登录状态"""
    input_username = st.session_state.username_input.strip()
    input_pwd = st.session_state.password_input.strip()
    
    if not input_username or not input_pwd:
        st.error("用户名/邮箱和密码不能为空")
        return
    
    user = users_collection.find_one({"$or": [
        {"username": input_username},
        {"email": input_username}
    ]})
    
    if not user:
        st.error("用户不存在，请检查用户名/邮箱")
        return
    
    if bcrypt.checkpw(input_pwd.encode('utf-8'), user["password"]):
        st.session_state.logged_in = True
        st.session_state.current_username = user["username"]
        st.session_state.username_input = ""
        st.session_state.password_input = ""
        st.success(f"欢迎回来，{st.session_state.current_username}！")
    else:
        st.error("密码错误，请重试")

def add_asset_to_db(asset_data):
    """添加新标的到数据库"""
    try:
        current_assets, _ = get_user_config_from_db()
        updated_assets = {**current_assets, **asset_data}
        users_collection.update_one(
            {"username": st.session_state.current_username},
            {"$set": {"assets_info": updated_assets}}
        )
        st.success("标的添加成功！")
        return True
    except Exception as e:
        st.error(f"添加失败：{str(e)}")
        return False
    
def update_asset_in_db(asset_data):
    """更新标的信息（主要用于调整持有数量）"""
    try:
        # 获取当前资产配置
        current_assets, _ = get_user_config_from_db()
        # 合并更新数据（覆盖原有标的信息）
        updated_assets = {** current_assets, **asset_data}
        # 执行数据库更新
        users_collection.update_one(
            {"username": st.session_state.current_username},
            {"$set": {"assets_info": updated_assets}}
        )
        st.success("标的信息更新成功！")
        return True
    except Exception as e:
        st.error(f"更新失败：{str(e)}")
        return False
    
def delete_asset_from_db(asset_name):
    """从数据库删除标的"""
    try:
        current_assets, _ = get_user_config_from_db()
        if asset_name in current_assets:
            del current_assets[asset_name]
            users_collection.update_one(
                {"username": st.session_state.current_username},
                {"$set": {"assets_info": current_assets}}
            )
            st.success(f"标的「{asset_name}」删除成功！")
            return True
        else:
            st.error("标的不存在，删除失败")
            return False
    except Exception as e:
        st.error(f"删除失败：{str(e)}")
        return False

# ========== 未登录状态 ==========
if not st.session_state.logged_in:
    st.subheader("请输入账号密码访问内容")
    st.text_input(
        "用户名/邮箱",
        key="username_input",
        placeholder="请输入用户名或邮箱"
    )
    st.text_input(
        "密码",
        type="password",
        key="password_input",
        on_change=check_password,
        placeholder="请输入密码"
    )

# ========== 已登录状态 ==========
else:
    st.set_page_config(page_title="资产组合查询器", layout="wide")
    st.title("📊 实时组合查询器")
    st.caption("自定义资产分类并管理标的，自动计算组合分布与调仓建议")

    # 实时读取配置
    assets_info, categories = get_user_config_from_db()
    target_ratio, target_ratio_sub = flatten_categories(categories)

    # 处理读取失败
    if not categories:
        st.error("获取配置失败，请重新登录")
        if st.button("重新登录"):
            st.session_state.logged_in = False
            st.session_state.current_username = ""
            st.rerun()
        st.stop()


    # ========== 显示当前持有的标的（更新备注展示） ==========
    st.markdown("---")
    st.subheader("📋 当前持有")

    if not assets_info:
        st.info("您暂无持有任何标的，可通过上方「添加新标的」功能录入资产")
    else:
        # 表头样式
        st.markdown("""
        <style>
        .asset-row {display: flex; align-items: center; padding: 8px 0; border-bottom: 1px solid #eee;}
        .asset-col {flex: 1; text-align: left; padding: 0 4px;}
        .asset-col-2 {flex: 2; text-align: left; padding: 0 4px;}
        .action-btn {flex: 1.2;}
        </style>
        """, unsafe_allow_html=True)
        
        # 表头
        st.markdown("""
        <div class="asset-row font-weight-bold">
            <div class="asset-col-2">标的名称</div>
            <div class="asset-col">标的代码</div>
            <div class="asset-col">类型</div>
            <div class="asset-col">持有份额</div>
            <div class="asset-col-2">分类</div>
            <div class="asset-col-2">备注</div>
            <div class="asset-col action-btn">操作</div>
        </div>
        """, unsafe_allow_html=True)
        
        # 标的列表
        for asset_name, asset_detail in assets_info.items():
            col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 1.5, 1, 1.5, 2, 2, 1.5])
            with col1:
                st.write(asset_name)
            with col2:
                st.write(asset_detail.get("code", ""))
            with col3:
                st.write(asset_detail.get("type", ""))
            with col4:
                st.write(f"{asset_detail.get('amount', 0.0):.2f}")
            with col5:
                st.write(asset_detail.get("category", "").split("-")[1])  # 保持与添加功能一致的分类显示
            with col6:
                st.write(asset_detail.get("remark", "无"))
            with col7:
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    edit_btn = st.button(
                        "编辑",
                        key=f"edit_{asset_name}",
                        use_container_width=True,
                        type="secondary"
                    )
                with btn_col2:
                    delete_btn = st.button(
                        "删除",
                        key=f"delete_{asset_name}",
                        use_container_width=True,
                        type="secondary"
                    )
                
                # 按钮点击逻辑
                if edit_btn:
                    st.session_state.edit_asset = asset_name
                    st.session_state.show_edit = True
                if delete_btn:
                    st.session_state.delete_confirm = True
                    st.session_state.asset_to_delete = asset_name

    # ========== 添加新标的功能 ==========
    # 初始隐藏添加表单，通过按钮控制显示状态
    if 'show_add_asset' not in st.session_state:
        st.session_state.show_add_asset = False

    # 显示"添加新标的"按钮（始终可见，点击切换表单显示状态）
    if st.button("➕ 添加新标的", type="primary"):
        st.session_state.show_add_asset = not st.session_state.show_add_asset

    # 当show_add_asset为True时，显示添加表单
    if st.session_state.show_add_asset:
        with st.form("add_asset_form"):
            col1, col2 = st.columns(2)
            with col1:
                asset_name = st.text_input("标的名称", placeholder="例如：十年国债")
                asset_code = st.text_input("标的代码（场内基金需要sh或sz）", placeholder="例如：sh511260")
                asset_type = st.selectbox("标的类型", ["fund", "etf", "cash"])
                asset_remark = st.text_input("备注", placeholder="例如：定投品种、风险提示等")
            with col2:
                hold_amount = st.number_input("持有份额", min_value=0.0, step=0.01, value=0.0)
                # 分类下拉框关联当前配置的小类
                asset_category = st.selectbox(
                    "所属分类",
                    options=list(target_ratio_sub.keys()),
                    format_func=lambda x: x.split("-")[1]  # 只显示小类名称
                )
                submit_asset = st.form_submit_button("确认添加", use_container_width=True)
            
            if submit_asset:
                new_asset = {
                    asset_name: {
                        "code": asset_code,
                        "type": asset_type,
                        "remark": asset_remark,  # 存储备注
                        "amount": hold_amount,
                        "category": asset_category
                    }
                }
                if add_asset_to_db(new_asset):
                    # 添加成功后自动隐藏表单
                    st.session_state.show_add_asset = False
                    st.rerun()

    # ========== 统一编辑弹窗（包含所有信息修改） ==========
    if st.session_state.get("show_edit", False) and st.session_state.get("edit_asset"):
        asset_name = st.session_state.edit_asset
        asset_detail = assets_info.get(asset_name, {})
        original_name = asset_name  # 保存原始名称用于更新键值
        
        st.markdown("---")
        with st.form(f"edit_asset_form_{asset_name}"):
            st.subheader(f"✏️ 编辑标的信息")
            
            # 两列布局展示编辑项
            col1, col2 = st.columns(2)
            with col1:
                # 标的名称（支持修改）
                new_name = st.text_input(
                    "标的名称",
                    value=asset_name,
                    placeholder="例如：十年国债"
                )
                
                # 标的代码
                new_code = st.text_input(
                    "标的代码（场内基金需要sh或sz）",
                    value=asset_detail.get("code", ""),
                    placeholder="例如：sh511260"
                )
                
                # 标的类型
                new_type = st.selectbox(
                    "标的类型",
                    ["fund", "etf", "cash"],
                    index=["fund", "etf", "cash"].index(asset_detail.get("type", "fund"))
                )
            
            with col2:
                # 持有份额
                new_amount = st.number_input(
                    "持有份额",
                    min_value=0.0,
                    step=0.01,
                    value=asset_detail.get("amount", 0.0)
                )
                
                # 所属分类
                new_category = st.selectbox(
                    "所属分类",
                    options=list(target_ratio_sub.keys()),
                    format_func=lambda x: x.split("-")[1],
                    index=list(target_ratio_sub.keys()).index(asset_detail.get("category", list(target_ratio_sub.keys())[0]))
                )
            
            # 备注（单独占一行）
            new_remark = st.text_area(
                "备注",
                value=asset_detail.get("remark", ""),
                placeholder="例如：定投品种、风险提示等",
                key=f"remark_{asset_name}"
            )
            
            # 操作按钮
            col_submit, col_cancel = st.columns(2)
            with col_submit:
                submit_edit = st.form_submit_button(
                    "确认保存",
                    use_container_width=True,
                    type="primary"
                )
            with col_cancel:
                cancel_edit = st.form_submit_button(
                    "取消",
                    use_container_width=True,
                    type="secondary"
                )
            
            if submit_edit:
                # 处理名称变更（需要删除旧键值）
                if original_name != new_name:
                    # 1. 先删除原始名称的记录
                    delete_asset_from_db(original_name)
                    # 2. 重新获取当前资产（因为已经删除了旧记录）
                    current_assets, _ = get_user_config_from_db()
                else:
                    current_assets, _ = get_user_config_from_db()
                
                # 构建更新数据
                updated_asset = {
                    new_name: {
                        "code": new_code,
                        "type": new_type,
                        "remark": new_remark,
                        "amount": new_amount,
                        "category": new_category
                    }
                }
                
                # 合并更新并保存
                final_assets = {**current_assets,** updated_asset}
                # 直接调用数据库更新（复用现有逻辑）
                try:
                    users_collection.update_one(
                        {"username": st.session_state.current_username},
                        {"$set": {"assets_info": final_assets}}
                    )
                    st.success("标的信息更新成功！")
                    st.session_state.show_edit = False
                    st.session_state.edit_asset = None
                    st.rerun()
                except Exception as e:
                    st.error(f"更新失败：{str(e)}")
            
            if cancel_edit:
                st.session_state.show_edit = False
                st.session_state.edit_asset = None
                st.rerun()

    # ========== 删除确认弹窗 ==========
    if st.session_state.delete_confirm:
        asset_name = st.session_state.asset_to_delete
        st.markdown("---")
        with st.form("delete_confirm_form"):
            st.subheader("⚠️ 确认删除")
            st.write(f"是否确定删除标的「**{asset_name}**」？此操作不可撤销。")
            
            col_confirm, col_cancel = st.columns(2)
            with col_confirm:
                confirm_delete = st.form_submit_button(
                    "✅ 确认删除", 
                    use_container_width=True, 
                    type="primary"
                )
            with col_cancel:
                cancel_delete = st.form_submit_button(
                    "❌ 取消", 
                    use_container_width=True, 
                    type="secondary"
                )
            
            if confirm_delete:
                if delete_asset_from_db(asset_name):
                    st.session_state.delete_confirm = False
                    st.session_state.asset_to_delete = ""
                    st.rerun()
            
            if cancel_delete:
                st.session_state.delete_confirm = False
                st.session_state.asset_to_delete = ""
                st.rerun()


    # ========== 资产组合计算功能 ==========
    if st.button("开始计算资产组合", use_container_width=True, type="primary"):
        from data_utils.Ashare import *
        from data_utils.utils import get_fund_price

        # 获取现有价值
        A = {}
        for name, info in assets_info.items():
            try:
                code = info["code"]
                source = info["type"]
                amount = info["amount"]
                if source == "fund":
                    A[name] = get_fund_price(code, count=1)
                elif source == "etf":
                    A[name] = get_price(code, frequency="5m", count=1)
            except Exception as e:
                st.warning(f"获取 {name} 数据失败：{e}")

        # 计算当前价值
        current_values = {}
        for name, info in assets_info.items():
            source = info["type"]
            amount = info["amount"]
            if source == "cash":
                current_values[name] = amount
            else:
                if name in A and not A[name].empty:
                    latest_price = A[name]["close"].iloc[-1]
                    current_values[name] = amount * latest_price
                else:
                    current_values[name] = 0.0

        # 构建资产明细DataFrame
        data = []
        for name, info in assets_info.items():
            data.append([
                info["code"],
                info["type"],
                info["amount"],
                info["category"],
                info.get("remark", "无"),  # 显示备注
                current_values[name]
            ])
        df = pd.DataFrame(data, index=assets_info.keys(),
                          columns=["代码", "类型", "持有份额", "分类", "备注", "现有价值"])
        df[["大类", "小类"]] = df["分类"].str.split("-", expand=True)

        # 总资产计算
        total_value = df["现有价值"].sum()

        # 小类汇总与差额分析
        sub_summary = df.groupby("分类")["现有价值"].sum()
        sub_diff = {}
        sub_diff_ratio = {}
        for k, tar in target_ratio_sub.items():
            target_value = total_value * tar
            actual_value = sub_summary.get(k, 0)
            sub_diff[k] = actual_value - target_value
            sub_diff_ratio[k] = sub_diff[k] / target_value * 100 if target_value != 0 else 0

        # 大类汇总与差额分析
        cls_summary = df.groupby("大类")["现有价值"].sum()
        cls_diff = {}
        cls_diff_ratio = {}
        for k, tar in target_ratio.items():
            target_value = total_value * tar
            actual_value = cls_summary.get(k, 0)
            cls_diff[k] = actual_value - target_value
            cls_diff_ratio[k] = cls_diff[k] / target_value * 100 if target_value != 0 else 0

        # 结果展示
        def highlight_diff(row):
            val = float(row["差额比例"][:-1])
            if val > 20:
                return ["background-color: #ff9999;"] * len(row)
            elif 10 < val <= 20:
                ratio = (val - 10) / 10
                r, g, b = 255, int(230 - ratio * 77), int(230 - ratio * 77)
                return [f"background-color: rgb({r},{g},{b});"] * len(row)
            elif val < -20:
                return ["background-color: #99ccff;"] * len(row)
            elif -20 <= val < -10:
                ratio = (abs(val) - 10) / 10
                r, g, b = int(230 - ratio * 77), int(240 - ratio * 36), 255
                return [f"background-color: rgb({r},{g},{b});"] * len(row)
            else:
                return [""] * len(row)

        st.markdown(f"### 投资组合总价值：{total_value:,.2f} 元")

        # 小类目标对比
        st.subheader("各小类目标对比")
        data_sub = []
        for k in target_ratio_sub:
            target_ratio_temp = round(target_ratio_sub[k] * 100, 2)
            current_ratio_temp = round(sub_summary.get(k, 0) / total_value * 100, 2)
            current_amount_temp = round(sub_summary.get(k, 0), 2)
            target_amount_temp = round(total_value * target_ratio_sub[k], 2)
            diff_ratio_temp = round(sub_diff_ratio[k], 2)
            diff_amount_temp = round(sub_diff[k], 2)
            data_sub.append({
                "现有金额": f"{current_amount_temp:.2f}",
                "当前比例": f"{current_ratio_temp:.2f}%",
                "目标金额": f"{target_amount_temp:.2f}",
                "目标比例": f"{target_ratio_temp:.2f}%",
                "差额金额": f"{diff_amount_temp:.2f}",
                "差额比例": f"{diff_ratio_temp:.2f}%"
            })
        sub_table = pd.DataFrame(data_sub, index=target_ratio_sub.keys())
        sub_table.index.name = "小类"
        st.table(sub_table.style.apply(highlight_diff, axis=1))

        # 大类目标对比
        st.subheader("各大类目标对比")
        cls_data = []
        for k in target_ratio:
            target_ratio_temp = round(target_ratio[k] * 100, 2)
            current_ratio_temp = round(cls_summary.get(k, 0) / total_value * 100, 2)
            current_amount_temp = round(cls_summary.get(k, 0), 2)
            target_amount_temp = round(total_value * target_ratio[k], 2)
            diff_ratio_temp = round(cls_diff_ratio[k], 2)
            diff_amount_temp = round(cls_diff[k], 2)
            cls_data.append({
                "现有金额": f"{current_amount_temp:.2f}",
                "当前比例": f"{current_ratio_temp:.2f}%",
                "目标金额": f"{target_amount_temp:.2f}",
                "目标比例": f"{target_ratio_temp:.2f}%",
                "差额金额": f"{diff_amount_temp:.2f}",
                "差额比例": f"{diff_ratio_temp:.2f}%"
            })
        cls_table = pd.DataFrame(cls_data, index=target_ratio.keys())
        cls_table.index.name = "大类"
        st.table(cls_table.style.apply(highlight_diff, axis=1))

        # 资产明细
        st.divider()
        st.subheader("当前资产明细（含价值）")
        st.dataframe(df[["代码", "类型", "持有份额", "现有价值", "分类", "备注"]], width='stretch')

        # 调仓建议
        st.markdown("---")
        st.subheader("📊 调仓建议（再平衡，阈值20%）")

        if df.empty or not target_ratio_sub:
            st.info("请先添加标的并设置目标配置比例，以生成调仓建议")
        else:
            total_value = df["现有价值"].sum()
            if total_value == 0:
                st.warning("所有标的现有价值为0，无法计算调仓建议")
            else:
                # 1. 计算当前比例（基于现有价值）和目标偏差
                category_value = df.groupby("分类")["现有价值"].sum().to_dict()
                current_ratio = {k: v / total_value for k, v in category_value.items()}
                
                adjustment = {}
                for category in target_ratio_sub:
                    if category == "机动-现金":
                        continue
                    target = target_ratio_sub[category]
                    current = current_ratio.get(category, 0.0)
                    diff_ratio = target - current  # 比例偏差（正数需增持，负数需减持）
                    diff_value = total_value * diff_ratio  # 价值偏差（元）
                    
                    # 计算偏差百分比（过滤<20%的调整，阈值改为20%）
                    deviation_pct = abs(diff_ratio) / target if target > 0 else 1.0
                    adjustment[category] = {
                        "目标比例": target,
                        "当前比例": current,
                        "比例偏差": diff_ratio,
                        "价值偏差": diff_value,
                        "偏差百分比": deviation_pct
                    }
                
                # 过滤偏差<20%的分类（只保留需要调仓的）
                significant_adj = {
                    k: v for k, v in adjustment.items() 
                    if v["偏差百分比"] >= 0.2 and v.get("类型") != "cash"  # 增加排除cash的条件
                }
                
                if not significant_adj:
                    st.success("所有资产类别偏差均小于20%，当前配置合理，无需调仓")
                else:
                    # 2. 大类偏离度展示
                    st.markdown("### 大类资产偏离度（偏差≥20%）")
                    major_deviation = {}
                    for category, adj in significant_adj.items():
                        major = category.split("-")[0]
                        major_deviation[major] = major_deviation.get(major, 0.0) + adj["偏差百分比"]
                    
                    major_cols = st.columns(len(major_deviation))
                    for i, (major, dev) in enumerate(major_deviation.items()):
                        with major_cols[i]:
                            st.metric(major, f"偏差 {dev:.0%}", "需调仓")
                    
                    # 3. 详细调仓建议
                    st.markdown("### 具体调仓操作建议")
                    for category, adj in significant_adj.items():
                        major, minor = category.split("-")
                        with st.expander(f"{major} - {minor}（偏差 {adj['偏差百分比']:.0%}）", expanded=True):
                            # 小类层面数据
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.write("目标比例")
                                st.subheader(f"{adj['目标比例']:.0%}")
                            with col2:
                                st.write("当前比例")
                                st.subheader(f"{adj['当前比例']:.0%}")
                            with col3:
                                st.write("价值调整")
                                if adj["价值偏差"] > 0:
                                    st.subheader(f"🔼 增持 {adj['价值偏差']:.2f}元")
                                else:
                                    st.subheader(f"🔽 减持 {abs(adj['价值偏差']):.2f}元")
                            
                            # 标的层面建议（优化卖出取整逻辑）
                            st.write("涉及标的调整（手数）：")
                            category_assets = df[df["分类"] == category].index.tolist()
                            if category_assets:
                                category_total = df.loc[category_assets, "现有价值"].sum()
                                for asset_name in category_assets:
                                    # 基础信息获取
                                    asset_type = df.loc[asset_name, "类型"]  # etf=场内，fund/cash=场外
                                    current_shares = df.loc[asset_name, "持有份额"]  # 当前持有份额
                                    unit_value = df.loc[asset_name, "现有价值"] / current_shares if current_shares > 0 else 1.0  # 单位净值
                                    
                                    # 计算单个标的需调整的价值（按比例分摊）
                                    asset_value_ratio = df.loc[asset_name, "现有价值"] / category_total
                                    asset_adjust_value = adj["价值偏差"] * asset_value_ratio
                                    
                                    # 计算调整份额（核心优化点）
                                    adjust_shares = 0
                                    shares_info = ""
                                    if unit_value > 0:
                                        base_shares = asset_adjust_value / unit_value  # 理论基础份额
                                        
                                        # 区分场内/场外 + 增持/减持，优化取整逻辑
                                        if asset_type == "etf":  # 场内标的（100份整数倍）
                                            if base_shares > 0:  # 增持
                                                # 向上取整到100的整数倍（确保达到最低增持需求）
                                                adjust_shares = (base_shares // 100) * 100
                                                shares_info = ""
                                            elif base_shares < 0:  # 减持
                                                # 向下取整到100的整数倍（不超过预期减持量）
                                                adjust_shares = (base_shares // 100 + 1) * 100
                                                # 额外校验：不超过当前持有份额（防止卖空）
                                                if abs(adjust_shares) > current_shares:
                                                    adjust_shares = -( (current_shares // 100) * 100 )
                                                shares_info = ""
                                        elif asset_type == "fund":  # 场外标的（精确到小数点后2位）
                                            if base_shares > 0:  # 增持
                                                adjust_shares = round(base_shares, 2)
                                                shares_info = ""
                                            elif base_shares < 0:  # 减持
                                                adjust_shares = round(base_shares, 2)
                                                # 额外校验：不超过当前持有份额
                                                if abs(adjust_shares) > current_shares:
                                                    adjust_shares = -round(current_shares, 2)
                                                shares_info = ""
                                    
                                    # 显示调仓建议
                                    if adjust_shares > 0:
                                        st.info(
                                            f"- 「{asset_name}」建议增持 {adjust_shares} 份额 {shares_info}\n"
                                            f"  对应价值：{adjust_shares * unit_value:.2f}元（单位净值：{unit_value:.2f}元）"
                                        )
                                    elif adjust_shares < 0:
                                        st.warning(
                                            f"- 「{asset_name}」建议减持 {abs(adjust_shares)} 份额 {shares_info}\n"
                                            f"  对应价值：{abs(adjust_shares) * unit_value:.2f}元（当前持有：{current_shares:.2f}份）"
                                        )
                            else:
                                st.info(f"- 该小类暂无标的，建议新增符合「{minor}」分类的标的")

        # 资产分布图表
        st.subheader("小类资产分布")
        fig1, ax1 = plt.subplots(figsize=(8, 6))
        ax1.pie(sub_summary.values, labels=sub_summary.index, autopct="%1.1f%%", startangle=90)
        ax1.axis("equal")
        st.pyplot(fig1)

        st.subheader("大类资产分布")
        fig2, ax2 = plt.subplots(figsize=(8, 6))
        ax2.pie(cls_summary.values, labels=cls_summary.index, autopct="%1.1f%%", startangle=90)
        ax2.axis("equal")
        st.pyplot(fig2)
        from datetime import datetime, timedelta

        # UTC时间+8小时=北京时间
        beijing_time = datetime.now()
        st.caption(f"更新时间：{beijing_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # ========== 分类配置功能（核心修改） ==========
    st.markdown("---")
    st.subheader("📁 资产分类配置")
    
    # 编辑/查看切换
    col_edit, col_reset = st.columns([1, 5])
    with col_edit:
        if st.button("编辑分类" if not st.session_state.edit_categories else "保存配置", use_container_width=True):
            if st.session_state.edit_categories:
                # 保存编辑
                if save_categories_to_db(st.session_state.temp_categories):
                    st.session_state.edit_categories = False
                    st.session_state.temp_categories = None
                    st.rerun()
            else:
                # 进入编辑模式，复制当前分类到临时变量
                st.session_state.edit_categories = True
                st.session_state.temp_categories = {**categories}  # 深拷贝

    with col_reset:
        if st.button("恢复默认分类", use_container_width=True, type="secondary"):
            if save_categories_to_db(DEFAULT_CATEGORIES):
                st.rerun()

    # 编辑模式下的操作
    if st.session_state.edit_categories and st.session_state.temp_categories is not None:
        temp_cats = st.session_state.temp_categories
        
        # 添加新大类
        st.markdown("### 添加新大类")
        new_major_name = st.text_input("新大类名称（例如：现金）", key="new_major")
        new_major_ratio = st.number_input(
            "新大类比例",
            min_value=0.01,
            max_value=0.99,
            value=0.10,
            step=0.01,
            format="%.2f",
            key="new_major_ratio"
        )
        if st.button("添加大类", key="add_major_btn") and new_major_name:
            if new_major_name not in temp_cats:
                temp_cats[new_major_name] = {
                    "ratio": new_major_ratio,
                    "subcategories": {"默认小类": new_major_ratio}  # 初始小类
                }
                st.session_state.temp_categories = temp_cats
                st.success(f"已添加大类「{new_major_name}」")
                st.rerun()
            else:
                st.error("该大类名称已存在")

        # 编辑现有大类和小类
        st.markdown("### 编辑现有分类")
        for major_name in list(temp_cats.keys()):  # 用list避免迭代中修改报错
            major_data = temp_cats[major_name]
            st.markdown(f"#### {major_name}")
            
            # 大类配置行
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                new_major_name = st.text_input(
                    "大类名称",
                    value=major_name,
                    key=f"major_name_{major_name}"
                )
            with col2:
                new_major_ratio = st.number_input(
                    "大类比例",
                    min_value=0.01,
                    max_value=0.99,
                    value=major_data["ratio"],
                    step=0.01,
                    format="%.2f",
                    key=f"major_ratio_{major_name}"
                )
            with col3:
                if st.button("删除大类", key=f"del_major_{major_name}", type="secondary"):
                    del temp_cats[major_name]
                    st.session_state.temp_categories = temp_cats
                    st.success(f"已删除大类「{major_name}」")
                    st.rerun()

            # 更新大类名称和比例
            if new_major_name != major_name:
                temp_cats[new_major_name] = temp_cats.pop(major_name)
                major_name = new_major_name  # 更新变量名
            temp_cats[major_name]["ratio"] = new_major_ratio

            # 小类配置
            st.caption("小类配置（总和需等于大类比例）")
            subcats = major_data["subcategories"]
            
            # 添加新小类
            col_add1, col_add2, col_add3 = st.columns([3, 2, 1])
            with col_add1:
                new_minor_name = st.text_input(
                    "新小类名称",
                    placeholder="例如：活期存款",
                    key=f"new_minor_{major_name}"
                )
            with col_add2:
                remaining_ratio = max(0.01, new_major_ratio - sum(subcats.values()))
                new_minor_ratio = st.number_input(
                    "小类比例",
                    min_value=0.01,
                    max_value=remaining_ratio + 1e-10,
                    value=min(0.05, remaining_ratio),
                    step=0.01,
                    format="%.2f",
                    key=f"new_minor_ratio_{major_name}"
                )
            with col_add3:
                if st.button("添加小类", key=f"add_minor_{major_name}") and new_minor_name:
                    if new_minor_name not in subcats:
                        subcats[new_minor_name] = new_minor_ratio
                        st.success(f"已添加小类「{new_minor_name}」")
                        st.rerun()
                    else:
                        st.error("该小类名称已存在")

            # 编辑现有小类
            for minor_name in list(subcats.keys()):
                col_min1, col_min2, col_min3 = st.columns([3, 2, 1])
                with col_min1:
                    new_minor_name = st.text_input(
                        "小类名称",
                        value=minor_name,
                        key=f"minor_name_{major_name}_{minor_name}"
                    )
                with col_min2:
                    other_sum = sum(v for k, v in subcats.items() if k != minor_name)
                    new_minor_ratio = st.number_input(
                        "小类比例",
                        value=subcats[minor_name],
                        step=0.01,
                        format="%.2f",
                        key=f"minor_ratio_{major_name}_{minor_name}"
                    )
                with col_min3:
                    if len(subcats) > 1:  # 至少保留一个小类
                        if st.button("删除", key=f"del_minor_{major_name}_{minor_name}", type="secondary"):
                            del subcats[minor_name]
                            st.success(f"已删除小类「{minor_name}」")
                            st.rerun()
                    else:
                        st.info("至少保留一个小类")

                # 更新小类名称和比例
                if new_minor_name != minor_name:
                    subcats[new_minor_name] = subcats.pop(minor_name)
                subcats[minor_name] = new_minor_ratio

            st.divider()

        st.info("⚠️ 所有大类比例总和需为100%，每个大类的小类比例总和需等于该大类比例")

    # 查看模式下的分类展示
    else:
        # 大类资产分类（横向展示）
        st.markdown("### 大类资产分类")
        if categories:
            # 根据大类数量创建对应列数（最多4列，超过自动换行）
            major_cols = st.columns(min(len(categories), 4))
            for i, (major_name, major_data) in enumerate(categories.items()):
                with major_cols[i % 4]:  # 超过4列时分行
                    st.metric(
                        major_name,
                        f"{major_data['ratio']:.0%}",
                        f"小类数量：{len(major_data['subcategories'])}个"
                    )

        # 小类资产分类（横向展示）
        st.markdown("### 小类资产分类")
        if categories:
            for major_name, major_data in categories.items():
                with st.expander(f"{major_name}（{major_data['ratio']:.0%}）"):
                    # 根据小类数量创建对应列数（最多4列，超过自动换行）
                    minor_cols = st.columns(min(len(major_data["subcategories"]), 4))
                    for i, (minor_name, minor_ratio) in enumerate(major_data["subcategories"].items()):
                        with minor_cols[i % 4]:  # 超过4列时分行
                            st.metric(
                                minor_name,
                                f"{minor_ratio:.0%}",
                                f"占大类比例：{minor_ratio/major_data['ratio']:.0%}"
                            )


    # 退出登录按钮
    st.markdown("---")
    if st.button("退出登录", use_container_width=True, type="primary"):
        st.session_state.logged_in = False
        st.session_state.current_username = ""
        st.rerun()