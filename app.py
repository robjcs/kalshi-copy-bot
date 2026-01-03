#!/usr/bin/env python3

import os
import time
import requests
import argparse
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from flask import Flask, render_template, jsonify, request
from dataclasses import dataclass, asdict
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class Trade:
    id: str
    market_ticker: str
    market_title: str
    side: str  # 'yes' or 'no'
    count: int
    yes_price: float
    no_price: float
    created_time: str
    user_id: str
    trade_type: str
    is_taker: bool
    copied: bool = False
    copy_timestamp: Optional[str] = None
    age_category: str = 'old'

class KalshiClient:
    def __init__(self, base_url: str = 'https://trading-api.kalshi.com/trade-api/v2'):
        self.base_url = base_url
        self.token = None
        self.user_id = None
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
    def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate with Kalshi API"""
        try:
            response = self.session.post(
                f"{self.base_url}/login",
                json={'email': email, 'password': password},
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            self.token = data['token']
            self.user_id = data['user_id']
            self.session.headers.update({'Authorization': f'Bearer {self.token}'})
            
            return data
        except Exception as e:
            raise Exception(f"Authentication failed: {str(e)}")
    
    def get_user_trades(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get trades for a specific user"""
        try:
            response = self.session.get(
                f"{self.base_url}/users/{user_id}/trades",
                params={'limit': limit},
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get('trades', [])
        except Exception as e:
            print(f"Error fetching trades: {str(e)}")
            return []
    
    def get_market(self, ticker: str) -> Dict[str, Any]:
        """Get market information"""
        try:
            response = self.session.get(f"{self.base_url}/markets/{ticker}", timeout=10)
            response.raise_for_status()
            return response.json().get('market', {})
        except Exception as e:
            print(f"Error fetching market {ticker}: {str(e)}")
            return {}
    
    def place_trade(self, ticker: str, side: str, count: int, price: float, order_type: str = 'market') -> Dict[str, Any]:
        """Place a trade"""
        try:
            response = self.session.post(
                f"{self.base_url}/markets/{ticker}/orders",
                json={
                    'side': side,
                    'count': count,
                    'price': price,
                    'type': order_type,
                    'action': 'buy'
                },
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Failed to place trade: {str(e)}")
    
    def is_authenticated(self) -> bool:
        return self.token is not None

def generate_dummy_trades() -> List[Dict[str, Any]]:
    """Generate dummy trade data for development"""
    markets = [
        "Will there be a major AI breakthrough announced in 2024?",
        "Will Trump win the 2024 presidential election?",
        "Will the Federal Reserve raise interest rates in March?",
        "Will Bitcoin be above $50,000 at the end of the year?",
        "Will the S&P 500 be above 4,500 by December 31st?",
        "Will US inflation be below 3% by end of Q4?",
        "Will Tesla stock be above $200 by end of year?",
        "Will there be a recession declared in 2024?",
    ]
    
    trades = []
    now = datetime.now()
    
    for i in range(15):
        # Generate trades with different ages for color coding demo
        if i < 3:
            # Recent trades (green)
            created_time = (now - timedelta(minutes=random.randint(1, 4))).isoformat() + 'Z'
        elif i < 7:
            # Hour old trades (yellow)
            created_time = (now - timedelta(minutes=random.randint(10, 50))).isoformat() + 'Z'
        elif i < 12:
            # Half day old trades (red)
            created_time = (now - timedelta(hours=random.randint(1, 10))).isoformat() + 'Z'
        else:
            # Old trades (white)
            created_time = (now - timedelta(hours=random.randint(15, 72))).isoformat() + 'Z'
            
        market_title = random.choice(markets)
        side = random.choice(['yes', 'no'])
        count = random.randint(1, 100)
        yes_price = random.randint(30, 85)
        no_price = 100 - yes_price
        
        trade = {
            'id': f'trade_{i:03d}',
            'market_ticker': f'MARKET-{i:03d}',
            'market_title': market_title,
            'side': side,
            'count': count,
            'yes_price': yes_price,
            'no_price': no_price,
            'created_time': created_time,
            'user_id': 'demo-trader-123',
            'trade_type': 'buy',
            'is_taker': random.choice([True, False])
        }
        trades.append(trade)
    
    # Sort trades by created_time in descending order (most recent first)
    trades.sort(key=lambda x: x['created_time'], reverse=True)
    
    return trades

class TradingBot:
    def __init__(self, demo_mode: bool = False):
        self.client = KalshiClient()
        self.target_user_id = ""
        self.trades: List[Trade] = []
        self.known_trade_ids = set()
        self.start_time = datetime.now()
        self.copied_count = 0
        self.is_monitoring = False
        self.max_copy_amount = 100
        self.auto_copy_enabled = True
        self.demo_mode = demo_mode
        self.demo_trades_data = []
        
        if self.demo_mode:
            self.demo_trades_data = generate_dummy_trades()
            print("🔥 Running in DEMO mode with dummy data")
        
    def authenticate(self, email: str, password: str):
        """Authenticate with Kalshi"""
        if self.demo_mode:
            return {'token': 'demo-token', 'user_id': 'demo-user', 'member_id': 'demo-member'}
        return self.client.authenticate(email, password)
    
    def set_target_user(self, user_id: str):
        """Set the target user to monitor"""
        self.target_user_id = user_id
        
    def get_trade_age_category(self, created_time: str) -> str:
        """Determine age category for color coding"""
        trade_time = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
        now = datetime.now(trade_time.tzinfo)
        minutes_ago = (now - trade_time).total_seconds() / 60
        
        if minutes_ago <= 5:
            return 'recent'  # Green
        elif minutes_ago <= 60:
            return 'hour'    # Yellow
        elif minutes_ago <= 720:  # 12 hours
            return 'halfday' # Red
        else:
            return 'old'     # White
    
    def convert_to_trade(self, trade_data: Dict[str, Any], copied: bool = False) -> Trade:
        """Convert API response to Trade object"""
        return Trade(
            id=trade_data['id'],
            market_ticker=trade_data['market_ticker'],
            market_title=trade_data['market_title'],
            side=trade_data['side'],
            count=trade_data['count'],
            yes_price=trade_data['yes_price'],
            no_price=trade_data['no_price'],
            created_time=trade_data['created_time'],
            user_id=trade_data['user_id'],
            trade_type=trade_data.get('trade_type', 'buy'),
            is_taker=trade_data.get('is_taker', True),
            copied=copied,
            copy_timestamp=datetime.now().isoformat() if copied else None,
            age_category=self.get_trade_age_category(trade_data['created_time'])
        )
    
    def load_initial_trades(self):
        """Load initial trades (don't copy historical ones)"""
        if not self.target_user_id:
            return
            
        if self.demo_mode:
            trades_data = self.demo_trades_data.copy()
        else:
            trades_data = self.client.get_user_trades(self.target_user_id, 50)
        
        # Mark all initial trades as known
        for trade_data in trades_data:
            self.known_trade_ids.add(trade_data['id'])
        
        # Convert to Trade objects, randomly mark some as copied for demo
        self.trades = []
        for trade_data in trades_data:
            copied = random.choice([True, False]) if self.demo_mode and random.random() < 0.3 else False
            if copied:
                self.copied_count += 1
            self.trades.append(self.convert_to_trade(trade_data, copied))
    
    def poll_for_new_trades(self):
        """Check for new trades"""
        if not self.target_user_id:
            return
            
        if self.demo_mode:
            # In demo mode, occasionally simulate a new trade
            if random.random() < 0.1:  # 10% chance per poll
                new_trade_data = {
                    'id': f'new_trade_{len(self.trades)}_{int(time.time())}',
                    'market_ticker': f'NEW-{random.randint(100, 999)}',
                    'market_title': random.choice([
                        'Will crypto prices surge this week?',
                        'Will the market close higher today?',
                        'Will there be major news announcement?'
                    ]),
                    'side': random.choice(['yes', 'no']),
                    'count': random.randint(1, 50),
                    'yes_price': random.randint(40, 80),
                    'no_price': lambda yp: 100 - yp,
                    'created_time': datetime.now().isoformat() + 'Z',
                    'user_id': self.target_user_id,
                    'trade_type': 'buy',
                    'is_taker': True
                }
                new_trade_data['no_price'] = 100 - new_trade_data['yes_price']
                
                if new_trade_data['id'] not in self.known_trade_ids:
                    self.known_trade_ids.add(new_trade_data['id'])
                    new_trade = self.convert_to_trade(new_trade_data, False)
                    self.trades.insert(0, new_trade)  # Add to beginning
                    
                    if self.auto_copy_enabled:
                        self.copy_trade(new_trade)
            return
            
        latest_trades_data = self.client.get_user_trades(self.target_user_id, 20)
        
        # Filter for new trades
        new_trades_data = []
        for trade_data in latest_trades_data:
            if (trade_data['id'] not in self.known_trade_ids and
                datetime.fromisoformat(trade_data['created_time'].replace('Z', '+00:00')) > self.start_time.replace(tzinfo=None).replace(tzinfo=datetime.now().astimezone().tzinfo)):
                new_trades_data.append(trade_data)
                self.known_trade_ids.add(trade_data['id'])
        
        if new_trades_data:
            # Convert to Trade objects
            new_trades = [self.convert_to_trade(trade_data, False) for trade_data in new_trades_data]
            
            # Add to beginning of trades list (newest first)
            self.trades = new_trades + self.trades
            
            # Auto-copy if enabled
            if self.auto_copy_enabled:
                for trade in new_trades:
                    self.copy_trade(trade)
    
    def copy_trade(self, trade: Trade) -> bool:
        """Copy a trade"""
        if trade.copied:
            return True
            
        try:
            if self.demo_mode:
                # In demo mode, just simulate copying
                print(f"Demo: Copying trade {trade.id} - {trade.side} {trade.count}@{trade.yes_price if trade.side == 'yes' else trade.no_price}c")
                time.sleep(0.1)  # Simulate API delay
            else:
                # Calculate copy amount
                copy_amount = min(trade.count, self.max_copy_amount)
                
                # Get current market info
                market = self.client.get_market(trade.market_ticker)
                if not market:
                    return False
                    
                # Use current market price
                current_price = market.get('yes_price' if trade.side == 'yes' else 'no_price', 0)
                
                # Place the trade
                self.client.place_trade(
                    trade.market_ticker,
                    trade.side,
                    copy_amount,
                    current_price,
                    'market'
                )
            
            # Mark as copied
            trade.copied = True
            trade.copy_timestamp = datetime.now().isoformat()
            self.copied_count += 1
            
            # Update in trades list
            for i, t in enumerate(self.trades):
                if t.id == trade.id:
                    self.trades[i] = trade
                    break
                    
            return True
            
        except Exception as e:
            print(f"Failed to copy trade {trade.id}: {str(e)}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bot statistics"""
        return {
            'total_trades': len(self.trades),
            'copied_trades': self.copied_count,
            'start_time': self.start_time.isoformat(),
            'is_monitoring': self.is_monitoring,
            'target_user_id': self.target_user_id,
            'last_update': datetime.now().isoformat()
        }

# Flask app
app = Flask(__name__)
bot = None  # Will be initialized in main

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/api/authenticate', methods=['POST'])
def authenticate():
    """Authenticate with Kalshi"""
    data = request.get_json()
    try:
        result = bot.authenticate(data['email'], data['password'])
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/set_target', methods=['POST'])
def set_target():
    """Set target user to monitor"""
    data = request.get_json()
    bot.set_target_user(data['user_id'])
    bot.load_initial_trades()
    return jsonify({'success': True})

@app.route('/api/trades')
def get_trades():
    """Get current trades"""
    # Update age categories
    for trade in bot.trades:
        trade.age_category = bot.get_trade_age_category(trade.created_time)
    
    # Poll for new trades
    bot.poll_for_new_trades()
    
    return jsonify({
        'trades': [asdict(trade) for trade in bot.trades],
        'stats': bot.get_stats()
    })

@app.route('/api/copy_trade', methods=['POST'])
def copy_trade():
    """Manually copy a specific trade"""
    data = request.get_json()
    trade_id = data['trade_id']
    
    # Find the trade
    for trade in bot.trades:
        if trade.id == trade_id:
            success = bot.copy_trade(trade)
            return jsonify({'success': success})
    
    return jsonify({'success': False, 'error': 'Trade not found'}), 404

@app.route('/api/status')
def get_status():
    """Get bot status including demo mode"""
    return jsonify({
        'demo_mode': bot.demo_mode,
        'is_authenticated': bot.client.is_authenticated() if not bot.demo_mode else True,
        'target_user_id': bot.target_user_id,
        'auto_copy_enabled': bot.auto_copy_enabled
    })

@app.route('/api/toggle_auto_copy', methods=['POST'])
def toggle_auto_copy():
    """Toggle auto-copy feature"""
    bot.auto_copy_enabled = not bot.auto_copy_enabled
    return jsonify({'auto_copy_enabled': bot.auto_copy_enabled})

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Kalshi Copy Bot')
    parser.add_argument('--demo', action='store_true', help='Run in demo mode with dummy data')
    args = parser.parse_args()
    
    # Initialize bot with demo mode
    bot = TradingBot(demo_mode=args.demo)
    
    # Load environment variables
    email = os.getenv('KALSHI_EMAIL')
    password = os.getenv('KALSHI_PASSWORD')
    target_user = os.getenv('TARGET_USER_ID')
    
    if args.demo:
        print("🔥 Running in DEMO mode - using dummy data")
        bot.set_target_user('demo-trader-123')
        bot.load_initial_trades()
        print(f"✅ Demo monitoring user: demo-trader-123 with {len(bot.trades)} trades")
    else:
        if email and password:
            try:
                bot.authenticate(email, password)
                print("✅ Authenticated with Kalshi")
            except Exception as e:
                print(f"❌ Authentication failed: {e}")
        
        if target_user:
            bot.set_target_user(target_user)
            bot.load_initial_trades()
            print(f"✅ Monitoring user: {target_user}")
    
    app.run(host='0.0.0.0', port=5001, debug=True)