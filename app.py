import streamlit as st
import pymongo
from pymongo import MongoClient
import bcrypt
from datetime import datetime
import time

# 页面配置
st.set_page_config(
    page_title="用户登录",
    page_icon="🔑",
    layout="centered"
)

# MongoDB 连接（与注册页保持一致）
@st.cache_resource
def init_connection():
    return MongoClient(st.secrets["mongo"]["conn_str"])  # 与注册页连接信息一致

client = init_connection()
db = client["user_db"]  # 与注册页数据库名称一致
users_collection = db["users"]  # 与注册页集合名称一致

# 密码验证（与注册时的加密对应）
def verify_password(password, hashed_password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password)

# 登录逻辑
def authenticate_user(username, password):
    # 支持用用户名或邮箱登录
    user = users_collection.find_one({"$or": [
        {"username": username},
        {"email": username}
    ]})
    
    if not user:
        return False, "用户名或密码不正确"
    if not verify_password(password, user["password"]):
        return False, "用户名或密码不正确"
    if not user.get("is_active", True):
        return False, "账号已被禁用，请联系管理员"
    
    # 更新最后登录时间
    users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.now()}}
    )
    return True, user["username"]  # 返回用户名用于会话存储

# 页面内容
st.title("🔑 用户登录")

# 显示刚注册的提示（可选）
if "just_registered" in st.session_state:
    st.info("注册成功，请使用您的账号登录")
    del st.session_state["just_registered"]  # 只显示一次

# 登录表单
with st.form("login_form"):
    st.subheader("请输入登录信息")
    username = st.text_input("用户名/邮箱", placeholder="请输入用户名或邮箱")
    password = st.text_input("密码", type="password", placeholder="请输入密码")
    remember_me = st.checkbox("记住我")  # 可后续扩展为持久化登录
    
    submit = st.form_submit_button("登录", use_container_width=True)
    
    if submit:
        if not username or not password:
            st.error("用户名/邮箱和密码都是必填项")
        else:
            success, result = authenticate_user(username, password)
            if success:
                # 登录成功，存储会话状态
                st.session_state["logged_in"] = True
                st.session_state["username"] = result  # 存储用户名
                st.success("登录成功！即将跳转到个人页面...")
                time.sleep(1)
                st.switch_page("pages/registration_page.py")  # 跳转
            else:
                st.error(result)

import os
# 打印当前页面文件的路径
st.write("当前登录页路径：", os.path.abspath(__file__))
# 打印 Streamlit 基准目录（应是 PortfolioChecker/）
st.write("Streamlit 基准目录：", os.getcwd())
import os
st.write("注册页是否存在：", os.path.exists(os.path.join(os.getcwd(), "PortfolioChecker/pages/registration_page.py")))

target_path = os.path.join(os.getcwd(), "PortfolioChecker/pages/registration_page.py")
st.write("目标注册页路径：", target_path)  # 确认此路径是否正确
# 没有账号？跳转到注册页
st.markdown("---")
st.write("还没有账号？")
if st.button("去注册", use_container_width=True):
    st.switch_page("PortfolioChecker/pages/registration_page.py")