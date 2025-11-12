import streamlit as st
import pymongo
from pymongo import MongoClient
import re
import bcrypt  # 用于密码加密
from datetime import datetime

# 页面配置
st.set_page_config(page_title="用户注册", page_icon="📝", layout="centered")

# MongoDB连接设置
@st.cache_resource
def init_connection():
    # 请替换为你的MongoDB连接字符串
    # 格式示例: "mongodb://username:password@host:port/" 或 "mongodb+srv://..."
    conn_str = st.secrets["mongo"]["conn_str"]
    return MongoClient(conn_str)

client = init_connection()

# 选择数据库和集合
db = client["user_db"]  # 数据库名称
users_collection = db["users"]  # 集合名称

# 密码加密函数
def hash_password(password):
    # 生成盐并加密密码
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed

# 验证密码函数
def verify_password(password, hashed_password):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password)

# 邮箱验证函数
def is_valid_email(email):
    pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
    return re.match(pattern, email) is not None

# 主注册函数
def register_user(username, email, password, confirm_password):
    # 表单验证
    if not username or not email or not password or not confirm_password:
        st.error("所有字段都是必填项，请完整填写")
        return False
    
    if password != confirm_password:
        st.error("两次输入的密码不一致")
        return False
    
    if len(password) < 1:
        st.error("密码长度至少为1个字符")
        return False
    
    if not is_valid_email(email):
        st.error("请输入有效的邮箱地址")
        return False
    
    # 检查用户名或邮箱是否已存在
    if users_collection.find_one({"username": username}):
        st.error("用户名已被注册")
        return False
    
    if users_collection.find_one({"email": email}):
        st.error("邮箱已被注册")
        return False
    
    # 密码加密
    hashed_password = hash_password(password)
    
    # 准备用户数据
    user_data = {
        "username": username,
        "email": email,
        "password": hashed_password,
        "created_at": datetime.now(),
        "last_login": None,
        "is_active": True
    }
    
    # 插入数据库
    try:
        users_collection.insert_one(user_data)
        st.success("注册成功！您现在可以登录了")
        return True
    except Exception as e:
        st.error(f"注册失败: {str(e)}")
        return False

# 页面标题
st.title("📝 用户注册")

# 注册表单
with st.form("registration_form"):
    st.subheader("请填写以下信息完成注册")
    
    username = st.text_input("用户名", placeholder="请输入用户名")
    email = st.text_input("邮箱", placeholder="请输入您的邮箱地址")
    password = st.text_input("密码", type="password", placeholder="请设置密码（至少1个字符）")
    confirm_password = st.text_input("确认密码", type="password", placeholder="请再次输入密码")
    
    # 提交按钮
    submit = st.form_submit_button("注册", use_container_width=True)
    
    if submit:
        register_user(username, email, password, confirm_password)

# 已有账号？跳转到登录页
st.markdown("---")

st.write("已有账号？")
if st.button("去登录", use_container_width=True):
    st.switch_page("app.py")