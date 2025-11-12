import requests
import pandas as pd
import re

def get_fund_price(code, count=500):
    """
    获取场外基金净值数据（默认日频）
    code: 基金代码 (str)，如 "006961"
    frequency: 暂时只支持 "d" (日线)
    count: 返回最近 N 条记录
    """
    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    r = requests.get(url)
    r.encoding = "utf-8"

    # 提取净值数据
    nav_data = re.search(r"Data_netWorthTrend\s*=\s*(.*?);", r.text).group(1)
    df = pd.DataFrame(eval(nav_data))  # [{'x':时间戳,'y':净值,'equityReturn':日涨幅}, ...]

    # 格式化 DataFrame
    df['date'] = pd.to_datetime(df['x'], unit='ms')
    df = df.set_index('date')
    df = df.rename(columns={'y': 'close'})[['close']]  # 保持与 get_price 接口一致

    # 只取最近 count 条
    if count is not None:
        df = df.tail(count)

    return df
