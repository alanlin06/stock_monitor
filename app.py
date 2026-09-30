import pandas as pd

def filter_institutional_radars(df):
    """
    輸入包含以下欄位的 DataFrame：
    - 股票代號 (Stock)
    - 價格模型 (Price_Model)
    - 外資雷達 (Foreign_Radar)
    - 投信雷達 (Investment_Trust_Radar)
    
    邏輯：
    1. 外資雷達：狀態為「建議買進」的股票清單
    2. 投信雷達：狀態為「建議買進」的股票清單
    3. 兩者獨立呈現於同一個報表
    """
    
    # 1. 篩選外資雷達狀態為「建議買進」的個股
    foreign_buy = df[df['Foreign_Radar'] == '建議買進'][['Stock', 'Price_Model', 'Foreign_Radar']]
    
    # 2. 篩選投信雷達狀態為「建議買進」的個股
    trust_buy = df[df['Investment_Trust_Radar'] == '建議買進'][['Stock', 'Price_Model', 'Investment_Trust_Radar']]
    
    return foreign_buy, trust_buy

# ==========================================
# 範例測試資料
# ==========================================
if __name__ == "__main__":
    # 模擬上游模組輸出的總表資料
    data = {
        'Stock': ['台積電 (2330)', '聯發科 (2454)', '鴻海 (2317)', '廣達 (2382)', '聯電 (2303)'],
        'Price_Model': ['建議買進', '建議買進', '建議買進', '建議買進', '觀察'],
        'Foreign_Radar': ['建議買進', '觀察', '建議買進', '建議買進', '建議買進'],
        'Investment_Trust_Radar': ['建議買進', '建議買進', '觀察', '建議買進', '建議買進']
    }
    
    df_all = pd.DataFrame(data)
    
    print("--- 原始總表狀態 ---")
    print(df_all)
    print("\n" + "="*50 + "\n")
    
    # 執行篩選
    foreign_list, trust_list = filter_institutional_radars(df_all)
    
    # 呈現結果
    print("【外資雷達 - 建議買進名單】")
    print(foreign_list.to_string(index=False))
    print("\n" + "-"*50 + "\n")
    
    print("【投信雷達 - 建議買進名單】")
    print(trust_list.to_string(index=False))