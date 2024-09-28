from flask import Flask, render_template, request, g, redirect
import sqlite3
import requests
import os
import math
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('agg')

app = Flask(__name__)
database = "datafile.db"

def get_db():
    if not hasattr(g, "sqlite_db"):
        g.sqlite_db = sqlite3.connect(database)
    return g.sqlite_db

# 每次 HTTP request 完成時都算結束
@app.teardown_appcontext
def close_connection(exception):
    print("正在關閉 SQL connection")
    if hasattr(g, "sqlite_db"):
        g.sqlite_db.close()

@app.route("/")
def homepage():
    conn = get_db()
    cursor = conn.cursor()

    # 取得現金庫存資訊
    result = cursor.execute("select * from cash")
    cash_result = result.fetchall()
    
    # Calculate the sum
    taiwanese_dollars = 0
    us_dollars = 0
    for data in cash_result:
        taiwanese_dollars += data[1]
        us_dollars += data[2]
    
    r = requests.get('https://tw.rter.info/capi.php')
    currency = r.json()
    sum = math.floor(taiwanese_dollars + us_dollars * currency["USDTWD"]['Exrate'])


    # 取得股票資訊
    result2 = cursor.execute("select * from stock")
    stock_result = result2.fetchall()
    unique_list = []
    for data in stock_result:
        if data[1] not in unique_list:
            unique_list.append(data[1])
    # 計算股票總市值（用於計算資產佔比）
    total_stock_value = 0

    # 單一股票資訊
    stock_info = []
    for stock in unique_list:
        result = cursor.execute("select * from stock where stock_id = ?", (stock, ))
        result = result.fetchall()
        stock_cost = 0
        shares = 0
        for d in result:
            shares += d[2]
            stock_cost += d[2] * d[3] + d[4] + d[5] # 股數 * 單價 + 手續費 + 交易稅
        
        # 從 API 獲得股票資訊
        url = "https://www.twse.com.tw/exchangeReport/STOCK_DAY?respose=json&stockNo=" + stock
        response = requests.get(url)
        data = response.json()
        price_array = data["data"]
        price = price_array[len(price_array) - 1][6]
        current_price = float(price.replace(",", ""))
        # 單一股票總市值
        total_value = round(current_price * shares)
        total_stock_value += total_value
        # 單一股票平均成本
        avg_cost = round(stock_cost / shares, 2)
        # 單一股票報酬率
        rate_of_return = round((total_value - stock_cost) * 100 / stock_cost, 2)
        # 將計算完的內容加入 stock info
        stock_info.append({'stock_id': stock,'shares': shares, "current_price": current_price, 'stock_cost': stock_cost, 'total': total_value, 'average_cost': avg_cost, 'rate_of_return': rate_of_return})

    for stock in stock_info:
        stock['value_percentage'] = round(stock['total'] * 100 / total_stock_value, 2)

    # 資料視覺化 - 股票佔比圓餅圖
    if (len(stock_info)) != 0:
        labels = tuple(unique_list)
        sizes = [data["total"] for data in stock_info]
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.pie(sizes, labels=labels, autopct=None, shadow=None)
        fig.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
        plt.savefig("static/stock_piechart.jpg", dpi=200)
    else:
        try:
            os.remove("static/stock_piechart.jpg")
        except:
            pass

    # 資料視覺化 - 股票現金佔比圓餅圖
    if us_dollars != 0 or taiwanese_dollars != 0 or total_stock_value != 0 :
        labels = ('USD', 'NTD', 'Stock')
        sizes = [us_dollars * currency["USDTWD"]['Exrate'], taiwanese_dollars, total_stock_value]
        fig, ax = plt.subplots(figsize=(6, 5))
        ax.pie(sizes, labels=labels, autopct=None, shadow=None)
        fig.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
        plt.savefig("static/cash_stock_piechart.jpg", dpi=200)
    else:
        try:
            os.remove("static/cash_stock_piechart.jpg")
        except:
            pass


    data = {'show_stock_pic': os.path.exists("static/stock_piechart.jpg"), 'show_cash_stock_pic': os.path.exists("static/cash_stock_piechart.jpg"), 'ntd': taiwanese_dollars, 'usd': us_dollars, 'rate': currency["USDTWD"]['Exrate'], 'sum':sum, 'cash_result': cash_result, 'stock_info': stock_info}    

    return render_template("index.html", data=data)

@app.route("/cash")
def cash():
    return render_template("cash.html")

@app.route("/cash", methods=["POST"])
def submit_cash():
    taiwanese_dollars = 0
    us_dollars = 0

    # 取得輸入資訊
    if request.values["taiwanese-dollars"] != "":
        taiwanese_dollars = request.values["taiwanese-dollars"]
    if request.values["us-dollars"] != "":
        us_dollars = request.values["us-dollars"]
    note = request.values["note"]
    date = request.values["date"]

    # 與資料庫互動
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""insert into cash (taiwanese_dollars, us_dollars, note, date_info) values (?, ?, ?, ?)""", (taiwanese_dollars, us_dollars, note, date))
    conn.commit()

    return redirect("/")

@app.route("/cash_delete", methods=["POST"])
def cash_delete():
    id = request.values["id"]
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("delete from cash where transaction_id = ?", (id, ))
    conn.commit()

    return redirect("/")

@app.route("/stock")
def stock():
    return render_template("stock.html")

@app.route("/stock", methods=["POST"])
def submit_stock():
    processing_fee = 0

    # 取得輸入資訊
    stock_id = request.values["stock-id"]
    num = request.values["stock-num"]
    price = request.values["stock-price"]
    if request.values["processing-fee"] != "":
        processing_fee = request.values["processing-fee"]
    if request.values["tax"] != "":
        tax = request.values["tax"]
    date = request.values["date"]

    # 與資料庫互動
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""insert into stock(stock_id, stock_num, stock_price, processing_fee, tax, date_info) values (?, ?, ?, ?, ?, ?)""", (stock_id, num, price, processing_fee, tax, date))
    conn.commit()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True, port=3000)