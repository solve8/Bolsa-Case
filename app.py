from flask import Flask, render_template, request, jsonify
import yfinance as yf
import pandas as pd
import random
import json
import os
import webbrowser
import threading

app = Flask(__name__)

# Memoria temporal para la sesión actual
session_data = {}
history_log = []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/load_chart', methods=['POST'])
def load_chart():
    data = request.json
    ticker = data.get('ticker', 'AMD')
    timeframe = data.get('timeframe', '1d') # Soporta '1d', '1wk', '1h', etc.
    
    # Descargamos los últimos 5 años para tener margen
    df = yf.download(ticker, period="5y", interval=timeframe, progress=False)
    if df.empty:
        return jsonify({"error": "No se encontraron datos para ese ticker."})
    
    df.reset_index(inplace=True)
    
    # Aplanar columnas si yfinance devuelve MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]

    # Renombrar la columna de fecha según el timeframe
    date_col = 'Datetime' if 'Datetime' in df.columns else 'Date'
    
    chart_data = []
    for _, row in df.iterrows():
        # Formato que exige Lightweight Charts
        chart_data.append({
            "time": row[date_col].strftime('%Y-%m-%d'),
            "open": float(row['Open']),
            "high": float(row['High']),
            "low": float(row['Low']),
            "close": float(row['Close']),
            "value": float(row['Volume'])
        })
    
    # Elegimos un punto aleatorio: mínimo vela 100 para tener contexto, máximo -50 para ver el futuro
    min_index = 100
    max_index = len(chart_data) - 50
    random_idx = random.randint(min_index, max_index)
    
    visible_data = chart_data[:random_idx]
    future_data = chart_data[random_idx:]
    
    # Guardamos en sesión
    session_data['ticker'] = ticker
    session_data['timeframe'] = timeframe
    session_data['visible_data'] = visible_data
    session_data['future_data'] = future_data
    session_data['entry_price'] = visible_data[-1]['close']
    session_data['entry_date'] = visible_data[-1]['time']
    
    return jsonify({
        "chart_data": visible_data,
        "entry_price": session_data['entry_price'],
        "date": session_data['entry_date']
    })

@app.route('/api/evaluate', methods=['POST'])
def evaluate():
    data = request.json
    sl = float(data.get('sl'))
    tp = float(data.get('tp'))
    rationale = data.get('rationale', '')
    
    future = session_data['future_data']
    result = "Indeciso (Se acabó el historial sin tocar SL ni TP)"
    exit_price = 0
    exit_date = ""
    exit_index = len(future) # Por defecto, si no toca nada, mostramos todo lo que queda

    # Recorremos el futuro oculto para ver qué toca primero
    for i, candle in enumerate(future):
        if sl < tp: # Operación en LARGO (Buy)
            if candle['low'] <= sl:
                result = "Perdida (SL Tocado)"
                exit_price = sl
                exit_date = candle['time']
                exit_index = i
                break
            elif candle['high'] >= tp:
                result = "Ganancia (TP Tocado)"
                exit_price = tp
                exit_date = candle['time']
                exit_index = i
                break
        else: # Operación en CORTO (Sell)
            if candle['high'] >= sl:
                result = "Perdida (SL Tocado)"
                exit_price = sl
                exit_date = candle['time']
                exit_index = i
                break
            elif candle['low'] <= tp:
                result = "Ganancia (TP Tocado)"
                exit_price = tp
                exit_date = candle['time']
                exit_index = i
                break

    # AQUÍ ESTÁ LA MAGIA: Cortamos el array del futuro justo hasta la vela de salida (incluida)
    visible_future = future[:exit_index + 1]

    # Registrar la operación
    log_entry = {
        "ticker": session_data['ticker'],
        "timeframe": session_data['timeframe'],
        "entry_date": session_data['entry_date'],
        "entry_price": session_data['entry_price'],
        "sl": sl,
        "tp": tp,
        "exit_date": exit_date,
        "exit_price": exit_price,
        "result": result,
        "rationale": rationale
    }
    history_log.append(log_entry)

    return jsonify({
        "future_data": visible_future, # Enviamos solo la porción visible
        "log_entry": log_entry
    })

@app.route('/api/next_candle', methods=['POST'])
def next_candle():
    if not session_data.get('future_data'):
        return jsonify({"error": "No hay más datos en el futuro."})
    
    # 1. Sacamos la primera vela del futuro (ya no se puede deshacer)
    next_c = session_data['future_data'].pop(0)
    
    # 2. Actualizamos el presente
    session_data['visible_data'].append(next_c)
    session_data['entry_price'] = next_c['close']
    session_data['entry_date'] = next_c['time']
    
    return jsonify({
        "candle": next_c,
        "entry_price": session_data['entry_price'],
        "date": session_data['entry_date']
    })

@app.route('/api/export', methods=['GET'])
def export_log():
    return jsonify(history_log)

if __name__ == '__main__':
    threading.Timer(1.0, lambda: webbrowser.open('http://localhost:5000')).start()
    app.run(debug=False)
