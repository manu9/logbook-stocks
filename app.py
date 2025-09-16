import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import sqlite3
st.set_page_config(layout="wide")

# Para aplicar css
with open('./app/style.css') as f:
    st.html(f'<style>{f.read()}</style>')

def main():
    st.title("Watchlist Stock")

    col1, col2, col3 = st.columns(3)
    
    my_container = col1.container()
    with my_container:
        if 'my_text_input' not in st.session_state:
                st.session_state.my_text_input = ""
        st.text_input("Agregar Ticker:", key="my_text_input", on_change=process_input)
        
    get_bond_metric(col2)
    get_equity_risk_premium(col3)
    
    create_watchlist_dataframe()
    initialized_from_db()
    
    st.divider()
    
    load_charts()
    

def load_charts():
    df = st.session_state.data
    ticker_list = df['Ticker'].tolist()
    n = 3
    groups = []
    for i in range(0, len(ticker_list), n):
        groups.append(ticker_list[i:i+n])
    
    cols = st.columns(n)
    for group in groups:
        for i, ticker in enumerate(group):
            cols[i].image(f'https://finviz.com/chart.ashx?t={ticker}')

@st.dialog('Modal')
def modal_message(message):
    st.info(message)


def process_input():
    value = st.session_state.my_text_input.upper()
    st.session_state.my_text_input = ""
    ticker_exists = is_into_watchlist(value)
    if not ticker_exists:
        is_add = load_ticker_in_watchlist(value)
        if is_add:
            save_ticker(value)
        
        
def load_ticker_in_watchlist(ticker):
    is_add = False
    try:
        ticker_info = yf.Ticker(ticker).info
        new_row = pd.DataFrame({
            'Ticker': ticker,
            'Nombre': ticker_info['shortName'],
            'Industria': ticker_info['industry'],
            'MarketCap': ticker_info['marketCap'],
            'Close' : ticker_info['currentPrice'],
            'Change %' : ticker_info['regularMarketChangePercent'],
            'Drawdown' : get_drawdown(ticker_info),
            'Target Price': ticker_info['targetMeanPrice'],
            'Upside': get_upside(ticker_info),
            'P/E (ttm)' : ticker_info['trailingPE'],
            'P/E (fwd)': ticker_info['forwardPE'],
            'PEG': get_metric(ticker_info, 'trailingPegRatio'),
            'ROE': ticker_info['returnOnEquity'],
            'Earning Yield': get_earning_yield(ticker_info),
            'Debt to EBITDA': get_debt_to_ebitda(ticker_info),
            'Quick Ratio': get_metric(ticker_info, 'quickRatio'),
            'Op. Mrg': float(ticker_info['operatingMargins'])*100
            }, index=[len(st.session_state.data)])  
        st.session_state["data"] = pd.concat([st.session_state.data, new_row], axis=0)
        is_add = True
    except Exception as e:
        modal_message(f'Ticker {ticker} no encontrado.')
    return is_add

def save_ticker(ticker):
    try:
        conn = sqlite3.connect('stocklist.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO watchlist_stocks VALUES (?,?)''', ('marandc', ticker))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

def get_metric(ticker_info, metric):
    try:
        peg = ticker_info.get(metric)
        if peg == None:
            return '-'
        else:
            return f"{peg:.2f}"
    except:
        st.error(f'Error {metric}')

def get_drawdown(ticker_info):
    val = ticker_info['fiftyTwoWeekHighChangePercent']
    return (val)*100

def get_upside(ticker_info):
    close = ticker_info['currentPrice']
    target = ticker_info['targetMeanPrice']
    return (target/close-1)*100


def get_earning_yield(ticker_info):
    close = ticker_info['currentPrice']
    eps_ttm = ticker_info['trailingEps']
    return (eps_ttm/close)*100

def get_quick_ratio(ticker_info):
    quick_ratio = 0.0
    try:
        quick_ratio = ticker_info['quickRatio']
    except:
        pass
    
    return quick_ratio


def get_debt_to_ebitda(ticker_info):
    debt_to_ebitda = 0.0
    try:
        ebitda = ticker_info['ebitda']
        total_debt = ticker_info['totalDebt']
        debt_to_ebitda = (total_debt/ebitda)
    except:
        pass
    
    return debt_to_ebitda

    
def is_into_watchlist(value):
    if not value:
        return True
    df = st.session_state["data"]
    is_into = df['Ticker'].isin([value]).any()
    if is_into:
        modal_message(f"El ticker {value} ya existe.")
        return True
    else:
        return False


def create_watchlist_dataframe():
    columns = ['Ticker','Nombre','Industria','MarketCap','Close','Change %','Drawdown', 'Target Price',
               'Upside','P/E (ttm)','P/E (fwd)','PEG','ROE','Earning Yield','Debt to EBITDA',
               'Quick Ratio','Op. Mrg']
    if "data" not in st.session_state:
        st.session_state["data"] = pd.DataFrame(columns=columns)
    
    st.session_state["data"] = st.session_state["data"].sort_values(by='Upside', ascending=False)
    column_config = {column: st.column_config.Column(disabled=True) for column in columns}

    st.session_state["data"]["Eliminar"] = False
    # Make Delete be the first column
    st.session_state["data"] = st.session_state["data"][columns + ["Eliminar"]]

    fully_styled_df = (st.session_state["data"].style.apply(fully_style_columns, subset=['Change %','Upside'])
                       .apply(upside_columns, subset=['Upside'])
                       .apply(earning_yield_columns, subset=['Earning Yield'])
                       .apply(debt_to_ebitda_columns, subset=['Debt to EBITDA'])
                       .format(lambda x: f"{x / 1_000_000_000:.2f} B",subset=['MarketCap'])
                       .format('{:.2f}%',subset=['Change %','Drawdown','Upside','Earning Yield','Op. Mrg'])
                       .format('{:.2f}',subset=['Close','Target Price','P/E (ttm)','P/E (fwd)'
                                                ,'Debt to EBITDA'])
                       .format(lambda x: f"{x * 100:.2f} %",subset=['ROE']))
 
    st.data_editor(
        fully_styled_df,
        key="watchlist",
        on_change=callback,
        hide_index=True,
        column_config=column_config,
    )

def initialized_from_db():
    if "initialized" not in st.session_state:
        with st.spinner("waiting"):
            try:
                conn = sqlite3.connect('stocklist.db', check_same_thread=False)
                cursor = conn.cursor()
                cursor.execute('''SELECT ticker FROM watchlist_stocks WHERE USER="marandc"''')
                tickers = cursor.fetchall()
                for ticker in tickers:
                    load_ticker_in_watchlist(ticker[0])
            except:
                pass
            finally:
                st.session_state["initialized"] = True
                conn.close()
                st.rerun()

def upside_columns(col: pd.Series) -> list[str]:
    return ['color:blue; font-weight: bold;' if cell >= 15 else '' for cell in col]

def earning_yield_columns(col: pd.Series) -> list[str]:
    bond10y = float(st.session_state["Bond10Y"].replace('%',''))
    return ['color:blue; font-weight: bold;' if cell >= bond10y else '' for cell in col]

def debt_to_ebitda_columns(col: pd.Series) -> list[str]:
    return ['color:blue; font-weight: bold;' if cell <= 2.5 else 'color:red;' for cell in col]

def fully_style_columns(col: pd.Series) -> list[str]:
    return ['color:red;' if cell < 0 else 'color:green;' for cell in col]


def callback():
    edited_rows = st.session_state["watchlist"]["edited_rows"]
    rows_to_delete = []

    for idx, value in edited_rows.items():
        if value["Eliminar"] is True:
            rows_to_delete.append(idx)

    ticker = st.session_state["data"].iloc[rows_to_delete]['Ticker'].item()
    st.session_state["data"] = (
        st.session_state["data"].drop(rows_to_delete, axis=0).reset_index(drop=True)
    )
    delete_ticker(ticker)
    
def delete_ticker(ticker):
    try:
        conn = sqlite3.connect('stocklist.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute('''DELETE FROM watchlist_stocks WHERE USER=? AND TICKER=?''', ('marandc', ticker))
        conn.commit()
    except:
        pass
    finally:
        conn.close()


def get_bond_metric(col):
    headers = {
    'accept': '*/*',
    'accept-language': 'es-US,es;q=0.9',
    'origin': 'https://www.cnbc.com',
    'priority': 'u=1, i',
    'referer': 'https://www.cnbc.com/quotes/US10Y',
    'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    }

    params = {
        'symbols': 'US10Y',
        'requestMethod': 'itv',
        'noform': '1',
        'partnerId': '2',
        'fund': '1',
        'exthrs': '1',
        'output': 'json',
        'events': '1',
    }

    try:
        response = requests.get(
            'https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol',
            params=params,
            headers=headers,
        )
        
        obj_resp = response.json()
        name = obj_resp['FormattedQuoteResult']['FormattedQuote'][0]['name']
        last = obj_resp['FormattedQuoteResult']['FormattedQuote'][0]['last']
        change = obj_resp['FormattedQuoteResult']['FormattedQuote'][0]['change']
        st.session_state["Bond10Y"] = last
        col.metric(name, last, delta=change)
    except:
        pass
    
    
def get_equity_risk_premium(col):
    url = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/home.htm"
    try:
        # Fetch the main page content
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        text_erp = soup.find_all('span', class_='MsoNormal')[2].text
        equity_risk_premium = text_erp.split('(')[0].strip()
        col.metric("Equity Risk Premium", equity_risk_premium)
        
    except:
        pass

if __name__ == '__main__':
    main()