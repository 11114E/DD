import pandas as pd
import plotly.express as px
import os
from flask import Flask, render_template, request
from datetime import timedelta

app = Flask(__name__)

# Path to the directory where CSV files are stored
CSV_DIRECTORY = "/root/quiltracker"

# Disable caching for browser
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Compute Quil earned per minute and hour
def compute_metrics(df):
    df['Date'] = pd.to_datetime(df['Date'])
    df['Balance'] = df['Balance'].astype(float)

    # Calculate Quil earned per minute
    df['Time_Diff_Minutes'] = df.groupby('Peer ID')['Date'].diff().dt.total_seconds() / 60
    df['Quil_Per_Minute'] = df.groupby('Peer ID')['Balance'].diff() / df['Time_Diff_Minutes']
    df['Quil_Per_Minute'] = df['Quil_Per_Minute'].fillna(0)

    # Filter out large time gaps to avoid incorrect calculations
    df = df.loc[df['Time_Diff_Minutes'] < 120]

    # Calculate Quil per hour
    df['Quil_Per_Hour'] = df['Quil_Per_Minute'] * 60

    # Calculate hourly growth by grouping by 'Hour' and 'Peer ID'
    df['Hour'] = df['Date'].dt.floor('h')
    hourly_growth = df.groupby(['Peer ID', 'Hour'])['Balance'].last().reset_index()
    hourly_growth['Growth'] = hourly_growth.groupby('Peer ID')['Balance'].diff().fillna(0)

    # Calculate Quil per hour for each hour
    hourly_growth['Quil_Per_Hour'] = hourly_growth['Growth']

    return df, hourly_growth

# Route to update balance data
@app.route('/update_balance', methods=['POST'])
def update_balance():
    try:
        data = request.get_json()
        print(f"Received data: {data}")

        if not data or 'peer_id' not in data or 'balance' not in data or 'timestamp' not in data or 'hostname' not in data:
            return 'Invalid data', 400

        peer_id = data['peer_id']
        balance = data['balance']
        timestamp = data['timestamp']
        hostname = data['hostname']

        log_file = os.path.join(CSV_DIRECTORY, f'node_balance_{peer_id}.csv')

        if not os.path.exists(log_file):
            with open(log_file, 'w') as f:
                f.write('Date,Peer ID,Balance,Hostname\n')

        with open(log_file, 'a') as f:
            f.write(f'{timestamp},{peer_id},{balance},{hostname}\n')

        print(f"Logged balance for {peer_id}: {balance} at {timestamp} from {hostname}")
        return 'Balance updated', 200
    except Exception as e:
        print(f"Error updating balance: {e}")
        return 'Internal Server Error', 500

# Main dashboard route
@app.route('/')
def index():
    data_frames = []
    night_mode = request.args.get('night_mode', 'off')

    # Read and combine all CSV files
    for file_name in os.listdir(CSV_DIRECTORY):
        if file_name.endswith('.csv'):
            file_path = os.path.join(CSV_DIRECTORY, file_name)
            print(f"Reading CSV file: {file_path}")
            df = pd.read_csv(file_path)

            if df['Balance'].dtype == 'object':
                df['Balance'] = df['Balance'].str.extract(r'([\d\.]+)').astype(float)

            data_frames.append(df)

    # Combine all data into a single dataframe
    if data_frames:
        combined_df = pd.concat(data_frames)
        combined_df['Date'] = pd.to_datetime(combined_df['Date'])
        combined_df.sort_values('Date', inplace=True)

        # Compute Quil earned per minute and hour
        combined_df, hourly_growth_df = compute_metrics(combined_df)

        # Prepare table data for rendering
        latest_balances = combined_df.groupby('Peer ID').last().reset_index()
        latest_balances['Hostname'] = combined_df.groupby('Peer ID')['Hostname'].last().values

        table_data = latest_balances[['Hostname', 'Balance', 'Quil_Per_Minute', 'Quil_Per_Hour']].reset_index()
        table_data = table_data.to_dict(orient='records')

        # Plot: Node Balances Over Time
        balance_fig = px.line(combined_df, x='Date', y='Balance', color='Peer ID', title='Node Balances Over Time')
        quil_per_minute_fig = px.bar(combined_df, x='Date', y='Quil_Per_Minute', color='Peer ID', title='Quil Earned Per Minute')
        
        chart_template = 'plotly_dark' if night_mode == 'on' else 'plotly'
        balance_fig.update_layout(template=chart_template)
        quil_per_minute_fig.update_layout(template=chart_template)

        # Convert Plotly figures to HTML for rendering
        balance_graph_html = balance_fig.to_html(full_html=False)
        quil_minute_graph_html = quil_per_minute_fig.to_html(full_html=False)

    else:
        table_data = []
        balance_graph_html = quil_minute_graph_html = ""

    return render_template('index.html', table_data=table_data,
                           balance_graph_html=balance_graph_html,
                           quil_minute_graph_html=quil_minute_graph_html,
                           night_mode=night_mode)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)