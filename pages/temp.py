import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
import matplotlib as mpl
from datetime import datetime

# 设置中文字体
mpl.font_manager.fontManager.addfont('PortfolioChecker/font/NotoSansSC-VariableFont_wght.ttf')
plt.rcParams['font.sans-serif']=['Noto Sans SC']
plt.rcParams['axes.unicode_minus']=False

from passlib.context import CryptContext

# 初始化加密上下文（用于验证密码）
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# 从 secrets 读取密码哈希-内容映射
USER_CONTENT_MAP = st.secrets["user_content"]

# 初始化 session_state
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_content" not in st.session_state:
    st.session_state.user_content = None  # 存储当前用户的专属内容
if "password_input" not in st.session_state:
    st.session_state.password_input = ""


def check_password():
    """验证密码并获取对应的专属内容"""
    input_pwd = st.session_state.password_input
    for hashed_pwd, content in USER_CONTENT_MAP.items():
        if pwd_context.verify(input_pwd, hashed_pwd):
            # 密码匹配，记录内容并标记登录
            st.session_state.logged_in = True
            st.session_state.user_content = content
            st.session_state.password_input = ""
            return
    st.error("密码错误，请重试")


# 未登录时显示密码输入
if not st.session_state.logged_in:
    st.subheader("请输入密码访问内容（输入 1 查看demo）")
    st.text_input(
        "密码",
        type="password",
        key="password_input",
        on_change=check_password,
        placeholder="输入密码后回车（输入 1 查看demo）"
    )

# 登录成功后展示专属内容（根据内容类型动态渲染）
else:
    st.success("登录成功！")
    
    # 根据当前密码展示对应的内容
    st.write("---")

    content = st.session_state.user_content

    # === 导入你自己的模块 ===
    from data_utils.Ashare import *
    from data_utils.utils import get_fund_price
    # from my_assets import assets_info, target_ratio, target_ratio_sub
    # 从用户专属内容中取出不同部分
    assets_info = content["assets_info"]
    target_ratio = content["target_ratio"]
    target_ratio_sub = content["target_ratio_sub"]

    # ========== Streamlit 页面配置 ==========
    st.set_page_config(page_title="资产组合查询器", layout="centered")
    st.title("实时组合查询器")
    st.caption("输入资产配置文件后自动计算当前分布、差额与调仓建议")

    if st.button("开始计算资产组合"):
        # === 获取现有价值 ===
        A = {}
        for name, info in assets_info.items():
            try:
                code = info["code"]
                source = info["type"]  # 这里注意，你原代码 source 是 fund/etf 类型
                data_source = info["source"]  # 记录来源
                amount = info["amount"]
                if source == "fund":
                    A[name] = get_fund_price(code, count=1)
                elif source == "etf":
                    A[name] = get_price(code, frequency="5m", count=1)
            except Exception as e:
                st.warning(f"获取 {name} 数据失败：{e}")

        current_values = {}
        for name, info in assets_info.items():
            code = info["code"]
            source = info["type"]  # 这里注意，你原代码 source 是 fund/etf 类型
            data_source = info["source"]  # 记录来源
            amount = info["amount"]
            if source == "cash":
                current_values[name] = amount
            else:
                latest_price = A[name]["close"].iloc[-1]
                current_values[name] = amount * latest_price
        data = []
        for name, info in assets_info.items():
            data.append([
                info["code"],
                info["source"],
                info["type"],
                info["amount"],
                info["category"]
            ])
        # === 转换成 DataFrame ===
        df = pd.DataFrame(data, index=assets_info.keys(),
                  columns=["代码", "渠道", "类型", "持有份额", "分类"])
        df["现有价值"] = [current_values[k] for k in df.index]
        df[["大类", "小类"]] = df["分类"].str.split("-", expand=True)

        # === 总资产 ===
        total_value = df["现有价值"].sum()

        # === 小类汇总 ===
        sub_summary = df.groupby("分类")["现有价值"].sum()
        sub_diff = {}
        sub_diff_ratio = {}
        for k, tar in target_ratio_sub.items():
            target_value = total_value * tar
            actual_value = sub_summary.get(k, 0)
            sub_diff[k] = actual_value - target_value
            sub_diff_ratio[k] = sub_diff[k] / target_value * 100

        # === 大类汇总 ===
        cls_summary = df.groupby("大类")["现有价值"].sum()
        cls_diff = {}
        cls_diff_ratio = {}
        for k, tar in target_ratio.items():
            target_value = total_value * tar
            actual_value = cls_summary.get(k, 0)
            cls_diff[k] = actual_value - target_value
            cls_diff_ratio[k] = cls_diff[k] / target_value * 100

        # === 输出结果区 ===
        def highlight_diff(row):
            val = float(row["差额比例"][:-1])  # 去掉%并转成浮点数
            
            # 超配：正差额
            if val > 20:
                return ["background-color: #ff9999;"] * len(row)  # 深红
            elif 10 < val <= 20:
                # 渐变从浅红 (#ffe6e6) → 深红 (#ff9999)
                ratio = (val - 10) / 10  # 0~1之间
                r = int(255)
                g = int(230 - ratio * (230 - 153))
                b = int(230 - ratio * (230 - 153))
                color = f"background-color: rgb({r},{g},{b});"
                return [color] * len(row)
            
            # 低配：负差额
            elif val < -20:
                return ["background-color: #99ccff;"] * len(row)  # 深蓝
            elif -20 <= val < -10:
                # 渐变从浅蓝 (#e6f0ff) → 深蓝 (#99ccff)
                ratio = (abs(val) - 10) / 10  # 0~1之间
                r = int(230 - ratio * (230 - 153))
                g = int(240 - ratio * (240 - 204))
                b = int(255)
                color = f"background-color: rgb({r},{g},{b});"
                return [color] * len(row)
            
            else:
                return [""] * len(row)

            
        st.markdown(f"**投资组合总价值：{total_value:,.2f} 元**")

        # === 差额分析 ===
        # === 各小类目标对比 ===
        st.subheader("各小类目标对比")
        data_sub = []
        for k in target_ratio_sub:
            # 计算各指标（强制四舍五入为2位小数）
            target_ratio_temp = round(target_ratio_sub[k] * 100, 2)
            current_ratio_temp = round(sub_summary.get(k, 0) / total_value * 100, 2)
            current_amount_temp = round(sub_summary.get(k, 0), 2)
            target_amount_temp = round(total_value * target_ratio_sub[k], 2)
            diff_ratio_temp = round(sub_diff_ratio[k], 2)
            diff_amount_temp = round(sub_diff[k], 2)
            
            # 转为字符串（固定两位小数格式，彻底避免浮点数精度问题）
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
        
        st.table(
            sub_table.style.apply(highlight_diff, axis=1)
        )

        # === 各大类目标对比 ===
        st.subheader("各大类目标对比")
        cls_data = []
        for k in target_ratio:
            # 计算各指标（强制四舍五入为2位小数）
            target_ratio_temp = round(target_ratio[k] * 100, 2)
            current_ratio_temp = round(cls_summary.get(k, 0) / total_value * 100, 2)
            current_amount_temp = round(cls_summary.get(k, 0), 2)  # 大类现有金额
            target_amount_temp = round(total_value * target_ratio[k], 2)  # 大类目标金额
            diff_ratio_temp = round(cls_diff_ratio[k], 2)
            diff_amount_temp = round(cls_diff[k], 2)
            
            # 转为字符串（固定两位小数格式）
            cls_data.append({
                "现有金额": f"{current_amount_temp:.2f}",
                "当前比例": f"{current_ratio_temp:.2f}%",
                "目标金额": f"{target_amount_temp:.2f}",
                "目标比例": f"{target_ratio_temp:.2f}%",
                "差额金额": f"{diff_amount_temp:.2f}",
                "差额比例": f"{diff_ratio_temp:.2f}%"
            })

        # 构建DataFrame
        cls_table = pd.DataFrame(cls_data, index=target_ratio.keys())

        cls_table.index.name = "大类"

        # 应用高亮样式
        st.table(
            cls_table.style.apply(highlight_diff, axis=1)
        )
        
        st.divider()
        st.subheader("当前资产明细")
        st.dataframe(df[["代码", "类型", "持有份额", "现有价值", "大类", "小类"]], width='stretch')

        # === 调仓建议 ===
        adjust = {}
        for k, v in sub_summary.items():
            diff_ratio = sub_diff_ratio[k]
            if diff_ratio > 0:
                for name, info in assets_info.items():
                    code = info["code"]
                    source = info["type"]  # 这里注意，你原代码 source 是 fund/etf 类型
                    data_source = info["source"]  # 记录来源
                    amount = info["amount"]
                    cls = info["category"]
                    if source == "fund" and cls == k:
                        latest_price = A[name]["close"].iloc[-1]
                        diff_val = sub_diff.get(k, 0)
                        shares_to_adjust = -diff_val / latest_price
                        if shares_to_adjust != 0:
                            adjust[name] = {
                                "代码": code,
                                "现价": latest_price,
                                "持仓份额": amount,
                                "目标调整手数": int(shares_to_adjust * 100) / 100,
                                "调整金额": int(shares_to_adjust * 100) / 100 * latest_price,
                                "所属小类": k
                            }
                        break

            elif diff_ratio < 0:
                for name, info in assets_info.items():
                    code = info["code"]
                    source = info["type"]  # 这里注意，你原代码 source 是 fund/etf 类型
                    data_source = info["source"]  # 记录来源
                    amount = info["amount"]
                    cls = info["category"]
                    if source == "etf" and cls == k:
                        latest_price = A[name]["close"].iloc[-1]
                        diff_val = sub_diff.get(k, 0)
                        shares_to_adjust = -diff_val / latest_price
                        lots_to_adjust = int(shares_to_adjust / 100)
                        if lots_to_adjust != 0:
                            adjust[name] = {
                                "代码": code,
                                "现价": latest_price,
                                "持仓份额": amount,
                                "目标调整手数": lots_to_adjust,
                                "调整金额": lots_to_adjust * 100 * latest_price,
                                "所属小类": k
                            }
                        break

        st.subheader("调仓建议")
        if not adjust:
            st.info("所有资产已满足目标比例，无需调整。")
        else:
            st.dataframe(pd.DataFrame(adjust).T, width='stretch')


        # === 小类饼图 ===
        st.subheader("小类资产分布")
        fig1, ax1 = plt.subplots()
        ax1.pie(sub_summary.values, labels=sub_summary.index, autopct="%1.1f%%", startangle=90)
        ax1.axis("equal")
        st.pyplot(fig1)

        # === 大类饼图 ===
        st.subheader("大类资产分布")
        fig2, ax2 = plt.subplots()
        ax2.pie(cls_summary.values, labels=cls_summary.index, autopct="%1.1f%%", startangle=90)
        ax2.axis("equal")
        st.pyplot(fig2)

        from datetime import datetime
        now = datetime.now()
        st.caption(f"更新时间：{now.strftime('%Y-%m-%d %H:%M:%S')}")

    # 退出登录按钮
    if st.button("退出登录"):
        st.session_state.logged_in = False
        st.session_state.current_password = ""
        st.rerun()



