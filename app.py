import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from decimal import Decimal
import csv
import io
from sqlalchemy import inspect, text, func

# Inisialisasi ekstensi di luar factory function
db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # ==================== KONFIGURASI DATABASE UNTUK RENDER ====================
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

    # Konfigurasi database untuk Render
    database_url = os.environ.get('DATABASE_URL', 'sqlite:///app.db')

    # Fix untuk Render: postgres:// -> postgresql://
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # ==========================================================================

    # Inisialisasi ekstensi dengan aplikasi
    db.init_app(app)
    login_manager.init_app(app)

    # Setup login manager
    login_manager.login_view = 'login'
    login_manager.login_message = 'Silakan login untuk mengakses halaman ini.'
    login_manager.login_message_category = 'warning'

    return app

def init_database(app):
    """Inisialisasi database dengan recovery mechanism"""
    with app.app_context():
        try:
            print(f"Database URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
            print("Initializing database...")
            
            # Cek koneksi database - PAKAI text() wrapper untuk SQLAlchemy 2.0
            db.session.execute(text('SELECT 1'))
            print("Database connection OK")
            
            # Gunakan inspector untuk cek tabel yang sudah ada
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            print(f"Existing tables: {existing_tables}")
            
            # Buat tabel jika belum ada (menggunakan create_all yang aman)
            db.create_all()
            print("Tables created/verified")
            
            # Cek jika tabel users sudah ada dan memiliki data
            if 'users' in existing_tables:
                user_count = db.session.query(User).count()
                print(f"Found {user_count} existing users")
                
                # Jika tidak ada user, buat admin default
                if user_count == 0:
                    create_default_admin()
                else:
                    print("Users already exist, skipping admin creation")
            else:
                # Tabel users belum ada, buat admin default
                create_default_admin()
                
            # Cek dan buat default accounts jika belum ada
            create_default_accounts_if_needed()
            
            print("Database initialization complete")
            
        except Exception as e:
            print(f"Error initializing database: {str(e)}")
            # Fallback ke SQLite jika PostgreSQL error
            try:
                print("Trying SQLite fallback...")
                app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
                db.create_all()
                create_default_admin()
                create_default_accounts_if_needed()
                print("Fallback to SQLite database successful")
            except Exception as e2:
                print(f"Fallback also failed: {e2}")

def create_default_admin():
    """Buat user admin default jika belum ada"""
    try:
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin', email='admin@tandurbawang.com')
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print("Created default admin user: admin / admin123")
            return True
        else:
            print("Admin user already exists")
            return False
    except Exception as e:
        print(f"Error creating admin user: {e}")
        return False

def create_default_accounts_if_needed():
    """Buat akun default jika belum ada"""
    try:
        account_count = Account.query.count()
        if account_count == 0:
            print("No accounts found, creating default accounts...")
            
            default_accounts = [
                {'code': '1101', 'name': 'Kas', 'type': 'Aset', 'category': 'Kas & Bank', 'normal_balance': 'Debit'},
                {'code': '1201', 'name': 'Persediaan', 'type': 'Aset', 'category': 'Persediaan', 'normal_balance': 'Debit'},
                {'code': '1301', 'name': 'Peralatan', 'type': 'Aset', 'category': 'Aktiva Tetap', 'normal_balance': 'Debit'},
                {'code': '1311', 'name': 'Akumulasi Penyusutan', 'type': 'Aset Kontra', 'category': 'Aktiva Tetap', 'normal_balance': 'Kredit'},
                {'code': '2101', 'name': 'Utang Usaha', 'type': 'Liabilitas', 'category': 'Utang Lancar', 'normal_balance': 'Kredit'},
                {'code': '2102', 'name': 'Utang Bank', 'type': 'Liabilitas', 'category': 'Utang Jangka Panjang', 'normal_balance': 'Kredit'},
                {'code': '3101', 'name': 'Modal Disetor', 'type': 'Ekuitas', 'category': 'Modal', 'normal_balance': 'Kredit'},
                {'code': '3102', 'name': 'Prive', 'type': 'Ekuitas', 'category': 'Modal', 'normal_balance': 'Debit'},
                {'code': '3901', 'name': 'Ikhtisar Laba Rugi', 'type': 'Ekuitas', 'category': 'Laba Rugi', 'normal_balance': 'Kredit'},
                {'code': '4101', 'name': 'Penjualan', 'type': 'Pendapatan', 'category': 'Pendapatan Usaha', 'normal_balance': 'Kredit'},
                {'code': '4102', 'name': 'Penjualan Lain-lain', 'type': 'Pendapatan', 'category': 'Pendapatan Lain', 'normal_balance': 'Kredit'},
                {'code': '5101', 'name': 'Pembelian', 'type': 'Beban', 'category': 'Harga Pokok', 'normal_balance': 'Debit'},
                {'code': '5901', 'name': 'HPP', 'type': 'Beban', 'category': 'Harga Pokok', 'normal_balance': 'Debit'},
                {'code': '5201', 'name': 'Beban Transportasi', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
                {'code': '5202', 'name': 'Beban Tenaga Kerja', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
                {'code': '5203', 'name': 'Beban Sewa', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
                {'code': '5204', 'name': 'Beban Perbaikan', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
                {'code': '5205', 'name': 'Beban Listrik dan Air', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
                {'code': '5206', 'name': 'Beban Administrasi', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
                {'code': '5301', 'name': 'Beban Penyusutan', 'type': 'Beban', 'category': 'Beban Non-Operasional', 'normal_balance': 'Debit'}
            ]
            
            for acc in default_accounts:
                account = Account(
                    account_code=acc['code'],
                    account_name=acc['name'],
                    account_type=acc['type'],
                    category=acc['category'],
                    normal_balance=acc['normal_balance'],
                    is_active=True
                )
                db.session.add(account)
            
            db.session.commit()
            print(f"Created {len(default_accounts)} default accounts")
            return True
        else:
            print(f"Found {account_count} existing accounts")
            return False
    except Exception as e:
        print(f"Error creating default accounts: {e}")
        db.session.rollback()
        return False

# ==================== MODELS ====================
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Account(db.Model):
    __tablename__ = 'accounts'
    
    id = db.Column(db.Integer, primary_key=True)
    account_code = db.Column(db.String(20), unique=True, nullable=False)
    account_name = db.Column(db.String(200), nullable=False)
    account_type = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(100), nullable=False)
    normal_balance = db.Column(db.String(10), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'account_code': self.account_code,
            'account_name': self.account_name,
            'account_type': self.account_type,
            'category': self.category,
            'normal_balance': self.normal_balance,
            'description': self.description,
            'is_active': self.is_active
        }
    
    def get_balance(self, include_adjusting=True, include_closing=True):
        """Get current balance for this account"""
        from datetime import datetime
        query = db.session.query(
            func.sum(JournalEntry.debit).label('total_debit'),
            func.sum(JournalEntry.credit).label('total_credit')
        ).filter(JournalEntry.account_code == self.account_code)
        
        if not include_adjusting:
            query = query.filter(JournalEntry.entry_type == 'regular')
        if not include_closing:
            query = query.filter(JournalEntry.entry_type != 'closing')
        
        result = query.first()
        total_debit = result.total_debit or 0
        total_credit = result.total_credit or 0
        
        if self.normal_balance == 'Debit':
            return total_debit - total_credit
        else:
            return total_credit - total_debit

class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_number = db.Column(db.String(50), unique=True, nullable=False)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    description = db.Column(db.String(500), nullable=False)
    account_debit = db.Column(db.String(20), nullable=False)
    account_debit_name = db.Column(db.String(200), nullable=False)
    account_credit = db.Column(db.String(20), nullable=False)
    account_credit_name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reference = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('transactions', lazy=True))

class JournalEntry(db.Model):
    __tablename__ = 'journal_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    description = db.Column(db.String(500), nullable=False)
    account_code = db.Column(db.String(20), nullable=False)
    account_name = db.Column(db.String(200), nullable=False)
    debit = db.Column(db.Float, default=0)
    credit = db.Column(db.Float, default=0)
    reference = db.Column(db.String(100))
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'))
    adjusting_entry_id = db.Column(db.Integer, db.ForeignKey('adjusting_entries.id'))
    closing_entry_id = db.Column(db.Integer, db.ForeignKey('closing_entries.id'))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    entry_type = db.Column(db.String(20), default='regular')  # regular, adjusting, closing
    ledger_processed = db.Column(db.Boolean, default=True)
    ledger_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    transaction = db.relationship('Transaction', backref=db.backref('journal_entries', lazy=True))
    adjusting_entry = db.relationship('AdjustingEntry', backref=db.backref('journal_entries', lazy=True))
    closing_entry = db.relationship('ClosingEntry', backref=db.backref('journal_entries', lazy=True))
    user = db.relationship('User', backref=db.backref('journal_entries', lazy=True))

class AdjustingEntry(db.Model):
    __tablename__ = 'adjusting_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(500))
    account_debit_code = db.Column(db.String(20), nullable=False)
    account_debit_name = db.Column(db.String(200), nullable=False)
    account_credit_code = db.Column(db.String(20), nullable=False)
    account_credit_name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    adjustment_type = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posted_to_ledger = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref=db.backref('adjusting_entries', lazy=True))

class ClosingEntry(db.Model):
    __tablename__ = 'closing_entries'
    
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reference = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(500), nullable=False)
    account_debit_code = db.Column(db.String(20), nullable=False)
    account_debit_name = db.Column(db.String(200), nullable=False)
    account_credit_code = db.Column(db.String(20), nullable=False)
    account_credit_name = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    entry_type = db.Column(db.String(100))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    posted_to_ledger = db.Column(db.Boolean, default=True)
    
    user = db.relationship('User', backref=db.backref('closing_entries', lazy=True))

class IncomeStatement(db.Model):
    __tablename__ = 'income_statements'
    
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(50), nullable=False)
    revenue = db.Column(db.Float, default=0)
    hpp = db.Column(db.Float, default=0)
    gross_profit = db.Column(db.Float, default=0)
    operating_expenses = db.Column(db.Float, default=0)
    net_income = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Setup user loader untuk Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ==================== HELPER CLASSES ====================
class LedgerProcessor:
    def __init__(self, user_id):
        self.user_id = user_id
    
    def get_ledger_entries(self, account_code=None, start_date=None, end_date=None, 
                          include_adjusting=True, include_closing=True):
        """Get ledger entries with running balance"""
        query = JournalEntry.query.filter_by(
            created_by=self.user_id,
            ledger_processed=True
        )
        
        if account_code:
            query = query.filter_by(account_code=account_code)
        
        if start_date:
            query = query.filter(JournalEntry.date >= start_date)
        
        if end_date:
            query = query.filter(JournalEntry.date <= end_date)
        
        if not include_adjusting:
            query = query.filter(JournalEntry.entry_type != 'adjusting')
        
        if not include_closing:
            query = query.filter(JournalEntry.entry_type != 'closing')
        
        entries = query.order_by(JournalEntry.date, JournalEntry.id).all()
        
        running_balance = 0
        ledger_data = []
        
        for entry in entries:
            account = Account.query.filter_by(account_code=entry.account_code).first()
            
            if account and account.normal_balance == 'Debit':
                running_balance += entry.debit - entry.credit
            else:
                running_balance += entry.credit - entry.debit
            
            ledger_data.append({
                'entry': entry,
                'running_balance': running_balance
            })
        
        return ledger_data

    def get_account_balance(self, account_code, include_adjusting=True, include_closing=True):
        """Get current balance for specific account"""
        entries = self.get_ledger_entries(account_code, 
                                         include_adjusting=include_adjusting,
                                         include_closing=include_closing)
        if entries:
            return entries[-1]['running_balance']
        return 0

class TrialBalance:
    def __init__(self, period=None, include_adjusting=True, include_closing=False):
        self.period = period or datetime.now().strftime('%B %Y')
        self.accounts_data = []
        self.total_debit = 0
        self.total_credit = 0
        self.include_adjusting = include_adjusting
        self.include_closing = include_closing
        
    def add_account_balance(self, account, debit, credit):
        self.accounts_data.append({
            'account': account,
            'debit': debit,
            'credit': credit
        })
        self.total_debit += debit
        self.total_credit += credit
    
    def is_balanced(self):
        return abs(self.total_debit - self.total_credit) < 0.01
    
    def get_difference(self):
        return abs(self.total_debit - self.total_credit)
    
    def get_accounts_by_type(self, account_type):
        return [item for item in self.accounts_data if item['account'].account_type == account_type]
    
    def get_summary_by_type(self):
        summary = {}
        for item in self.accounts_data:
            acc_type = item['account'].account_type
            if acc_type not in summary:
                summary[acc_type] = {'debit': 0, 'credit': 0, 'count': 0}
            summary[acc_type]['debit'] += item['debit']
            summary[acc_type]['credit'] += item['credit']
            summary[acc_type]['count'] += 1
        return summary

class FinancialStatement:
    def __init__(self, period=None):
        self.period = period or datetime.now().strftime('%B %Y')
        self.income_statement = {}
        self.balance_sheet = {}
        
    def calculate_income_statement(self, trial_balance):
        """Calculate Income Statement according to accounting principles"""
        # Pendapatan (Revenue)
        revenue_accounts = trial_balance.get_accounts_by_type('Pendapatan')
        total_revenue = sum(item['credit'] - item['debit'] for item in revenue_accounts)
        
        # Harga Pokok Penjualan (HPP)
        hpp_accounts = [item for item in trial_balance.accounts_data 
                       if item['account'].account_code in ['5101', '5901']]
        total_hpp = sum(item['debit'] - item['credit'] for item in hpp_accounts)
        
        # Laba Kotor (Gross Profit)
        gross_profit = total_revenue - total_hpp
        
        # Beban Operasional
        operating_expenses_detailed = {
            'beban_transportasi': 0,
            'beban_tenaga_kerja': 0,
            'beban_sewa': 0,
            'beban_perbaikan': 0,
            'beban_penyusutan': 0,
            'beban_listrik_air': 0,
            'beban_administrasi': 0,
            'beban_lain_lain': 0,
            'total': 0
        }
        
        expense_accounts = [item for item in trial_balance.accounts_data 
                          if item['account'].account_type == 'Beban' 
                          and item['account'].account_code not in ['5101', '5901']]
        
        for item in expense_accounts:
            amount = item['debit'] - item['credit']
            account_code = item['account'].account_code
            
            if account_code == '5201':
                operating_expenses_detailed['beban_transportasi'] = amount
            elif account_code == '5202':
                operating_expenses_detailed['beban_tenaga_kerja'] = amount
            elif account_code == '5203':
                operating_expenses_detailed['beban_sewa'] = amount
            elif account_code == '5204':
                operating_expenses_detailed['beban_perbaikan'] = amount
            elif account_code == '5205':
                operating_expenses_detailed['beban_listrik_air'] = amount
            elif account_code == '5206':
                operating_expenses_detailed['beban_administrasi'] = amount
            elif account_code == '5301':
                operating_expenses_detailed['beban_penyusutan'] = amount
            else:
                operating_expenses_detailed['beban_lain_lain'] += amount
        
        operating_expenses_detailed['total'] = sum([
            operating_expenses_detailed['beban_transportasi'],
            operating_expenses_detailed['beban_tenaga_kerja'],
            operating_expenses_detailed['beban_sewa'],
            operating_expenses_detailed['beban_perbaikan'],
            operating_expenses_detailed['beban_penyusutan'],
            operating_expenses_detailed['beban_listrik_air'],
            operating_expenses_detailed['beban_administrasi'],
            operating_expenses_detailed['beban_lain_lain']
        ])
        
        net_income_before_tax = gross_profit - operating_expenses_detailed['total']
        
        self.income_statement = {
            'revenue': total_revenue,
            'hpp': total_hpp,
            'gross_profit': gross_profit,
            'operating_expenses': operating_expenses_detailed['total'],
            'operating_expenses_detailed': operating_expenses_detailed,
            'net_income': net_income_before_tax
        }
        
        return self.income_statement
    
    def calculate_balance_sheet(self, trial_balance, net_income):
        """Calculate Balance Sheet according to accounting principles"""
        asset_accounts = trial_balance.get_accounts_by_type('Aset')
        asset_contra_accounts = trial_balance.get_accounts_by_type('Aset Kontra')
        
        total_assets = sum(item['debit'] - item['credit'] for item in asset_accounts)
        
        kas_bank = 0
        persediaan = 0
        peralatan = 0
        akumulasi_penyusutan = 0
        
        for item in asset_accounts:
            amount = item['debit'] - item['credit']
            account_code = item['account'].account_code
            
            if account_code == '1101':
                kas_bank = amount
            elif account_code == '1201':
                persediaan = amount
            elif account_code == '1301':
                peralatan = amount
        
        for item in asset_contra_accounts:
            amount = item['credit'] - item['debit']
            account_code = item['account'].account_code
            
            if account_code == '1311':
                akumulasi_penyusutan = amount
        
        liability_accounts = trial_balance.get_accounts_by_type('Liabilitas')
        total_liabilities = sum(item['credit'] - item['debit'] for item in liability_accounts)
        
        utang_usaha = 0
        utang_bank = 0
        
        for item in liability_accounts:
            amount = item['credit'] - item['debit']
            account_code = item['account'].account_code
            
            if account_code == '2101':
                utang_usaha = amount
            elif account_code == '2102':
                utang_bank = amount
        
        equity_accounts = trial_balance.get_accounts_by_type('Ekuitas')
        initial_equity = 0
        prive = 0
        
        for item in equity_accounts:
            if item['account'].account_code == '3101':
                initial_equity = item['credit'] - item['debit']
            elif item['account'].account_code == '3102':
                prive = item['debit'] - item['credit']
        
        ending_equity = initial_equity + net_income - prive
        
        self.balance_sheet = {
            'assets': total_assets - akumulasi_penyusutan,
            'liabilities': total_liabilities,
            'equity': ending_equity,
            'initial_equity': initial_equity,
            'prive': prive,
            'assets_detailed': {
                'kas_bank': kas_bank,
                'persediaan': persediaan,
                'peralatan': peralatan,
                'akumulasi_penyusutan': akumulasi_penyusutan
            },
            'liabilities_detailed': {
                'utang_usaha': utang_usaha,
                'utang_bank': utang_bank
            }
        }
        
        return self.balance_sheet

class ClosingProcessor:
    def __init__(self, user_id, period=None):
        self.user_id = user_id
        self.period = period or datetime.now().strftime('%B %Y')
        self.closing_entries = []
        self.net_income = 0
        self.reference_counter = 1
        
    def _generate_unique_reference(self, entry_type):
        base_ref = f"CLS-{entry_type}-{datetime.now().strftime('%Y%m%d')}"
        unique_ref = f"{base_ref}-{self.reference_counter:03d}"
        self.reference_counter += 1
        return unique_ref
        
    def get_adjusted_trial_balance_data(self, include_closing=False):
        ledger_processor = LedgerProcessor(self.user_id)
        accounts = Account.query.filter_by(is_active=True).all()
        
        trial_balance_data = []
        
        for account in accounts:
            balance = ledger_processor.get_account_balance(account.account_code, 
                                                          include_adjusting=True,
                                                          include_closing=include_closing)
            
            if account.normal_balance == 'Debit':
                if balance >= 0:
                    trial_balance_data.append({
                        'account': account,
                        'debit': abs(balance),
                        'credit': 0
                    })
                else:
                    trial_balance_data.append({
                        'account': account,
                        'debit': 0,
                        'credit': abs(balance)
                    })
            else:
                if balance >= 0:
                    trial_balance_data.append({
                        'account': account,
                        'debit': 0,
                        'credit': abs(balance)
                    })
                else:
                    trial_balance_data.append({
                        'account': account,
                        'debit': abs(balance),
                        'credit': 0
                    })
        
        return trial_balance_data
    
    def get_income_statement_data(self, include_closing=False):
        trial_balance_data = self.get_adjusted_trial_balance_data(include_closing=include_closing)
        
        trial_balance_obj = TrialBalance(include_adjusting=True, include_closing=include_closing)
        for item in trial_balance_data:
            trial_balance_obj.add_account_balance(item['account'], item['debit'], item['credit'])
        
        financial_stmt = FinancialStatement()
        income_stmt = financial_stmt.calculate_income_statement(trial_balance_obj)
        
        return income_stmt['net_income']
    
    def generate_closing_entries(self):
        self.closing_entries = []
        
        trial_balance_data = self.get_adjusted_trial_balance_data(include_closing=False)
        self.net_income = self.get_income_statement_data(include_closing=False)
        
        # Close revenue accounts to Income Summary
        revenue_accounts = [item for item in trial_balance_data 
                          if item['account'].account_type == 'Pendapatan' and item['credit'] > 0]
        
        for item in revenue_accounts:
            entry = ClosingEntry(
                date=datetime.now(),
                reference=self._generate_unique_reference('REV'),
                description=f"Penutupan akun pendapatan {item['account'].account_name}",
                account_debit_code=item['account'].account_code,
                account_debit_name=item['account'].account_name,
                account_credit_code='3901',
                account_credit_name='Ikhtisar Laba Rugi',
                amount=item['credit'],
                entry_type='Pendapatan',
                created_by=self.user_id,
                posted_to_ledger=True
            )
            self.closing_entries.append(entry)
        
        # Close expense accounts to Income Summary
        expense_accounts = [item for item in trial_balance_data 
                          if item['account'].account_type == 'Beban' and item['debit'] > 0]
        
        for item in expense_accounts:
            entry = ClosingEntry(
                date=datetime.now(),
                reference=self._generate_unique_reference('EXP'),
                description=f"Penutupan akun beban {item['account'].account_name}",
                account_debit_code='3901',
                account_debit_name='Ikhtisar Laba Rugi',
                account_credit_code=item['account'].account_code,
                account_credit_name=item['account'].account_name,
                amount=item['debit'],
                entry_type='Beban',
                created_by=self.user_id,
                posted_to_ledger=True
            )
            self.closing_entries.append(entry)
        
        # Close HPP accounts to Income Summary
        hpp_accounts = [item for item in trial_balance_data 
                       if item['account'].account_code in ['5101', '5901'] and item['debit'] > 0]
        
        for item in hpp_accounts:
            entry = ClosingEntry(
                date=datetime.now(),
                reference=self._generate_unique_reference('HPP'),
                description=f"Penutupan akun {item['account'].account_name}",
                account_debit_code='3901',
                account_debit_name='Ikhtisar Laba Rugi',
                account_credit_code=item['account'].account_code,
                account_credit_name=item['account'].account_name,
                amount=item['debit'],
                entry_type='HPP',
                created_by=self.user_id,
                posted_to_ledger=True
            )
            self.closing_entries.append(entry)
        
        # Close Income Summary to Capital (Net Income/Loss)
        if self.net_income != 0:
            if self.net_income > 0:
                entry = ClosingEntry(
                    date=datetime.now(),
                    reference=self._generate_unique_reference('INCOME'),
                    description='Penutupan Ikhtisar Laba Rugi (Laba) ke Modal',
                    account_debit_code='3901',
                    account_debit_name='Ikhtisar Laba Rugi',
                    account_credit_code='3101',
                    account_credit_name='Modal Disetor',
                    amount=self.net_income,
                    entry_type='Laba Bersih',
                    created_by=self.user_id,
                    posted_to_ledger=True
                )
            else:
                entry = ClosingEntry(
                    date=datetime.now(),
                    reference=self._generate_unique_reference('LOSS'),
                    description='Penutupan Ikhtisar Laba Rugi (Rugi) ke Modal',
                    account_debit_code='3101',
                    account_debit_name='Modal Disetor',
                    account_credit_code='3901',
                    account_credit_name='Ikhtisar Laba Rugi',
                    amount=abs(self.net_income),
                    entry_type='Rugi Bersih',
                    created_by=self.user_id,
                    posted_to_ledger=True
                )
            self.closing_entries.append(entry)
        
        # Close Drawing accounts to Capital
        prive_accounts = [item for item in trial_balance_data 
                         if item['account'].account_code == '3102' and item['debit'] > 0]
        
        for item in prive_accounts:
            entry = ClosingEntry(
                date=datetime.now(),
                reference=self._generate_unique_reference('PRIVE'),
                description='Penutupan akun prive ke modal',
                account_debit_code='3101',
                account_debit_name='Modal Disetor',
                account_credit_code='3102',
                account_credit_name='Prive',
                amount=item['debit'],
                entry_type='Prive',
                created_by=self.user_id,
                posted_to_ledger=True
            )
            self.closing_entries.append(entry)
        
        return self.closing_entries
    
    def save_closing_entries(self):
        try:
            # First, delete existing closing entries
            existing_entries = ClosingEntry.query.filter_by(created_by=self.user_id).all()
            for entry in existing_entries:
                # Also delete associated journal entries
                JournalEntry.query.filter_by(closing_entry_id=entry.id).delete()
                db.session.delete(entry)
            
            # Add new closing entries
            for entry in self.closing_entries:
                db.session.add(entry)
                db.session.flush()  # Get the entry ID
                
                # Create journal entries for closing
                debit_journal = JournalEntry(
                    date=entry.date,
                    description=entry.description,
                    account_code=entry.account_debit_code,
                    account_name=entry.account_debit_name,
                    debit=entry.amount,
                    credit=0,
                    reference=entry.reference,
                    closing_entry_id=entry.id,
                    created_by=self.user_id,
                    entry_type='closing',
                    ledger_processed=True,
                    ledger_date=datetime.now()
                )
                
                credit_journal = JournalEntry(
                    date=entry.date,
                    description=entry.description,
                    account_code=entry.account_credit_code,
                    account_name=entry.account_credit_name,
                    debit=0,
                    credit=entry.amount,
                    reference=entry.reference,
                    closing_entry_id=entry.id,
                    created_by=self.user_id,
                    entry_type='closing',
                    ledger_processed=True,
                    ledger_date=datetime.now()
                )
                
                db.session.add(debit_journal)
                db.session.add(credit_journal)
            
            db.session.commit()
            return True, f"Berhasil menyimpan {len(self.closing_entries)} closing entries dan jurnal terkait"
        except Exception as e:
            db.session.rollback()
            return False, f"Gagal menyimpan closing entries: {str(e)}"

class PostClosingTrialBalance:
    def __init__(self, period=None):
        self.period = period or datetime.now().strftime('%B %Y')
        self.real_accounts_data = []
        self.total_debit = 0
        self.total_credit = 0
        
    def add_real_account_balance(self, account, debit, credit):
        if account.account_type in ['Aset', 'Liabilitas', 'Ekuitas']:
            self.real_accounts_data.append({
                'account': account,
                'debit': debit,
                'credit': credit
            })
            self.total_debit += debit
            self.total_credit += credit
    
    def is_balanced(self):
        return abs(self.total_debit - self.total_credit) < 0.01
    
    def get_difference(self):
        return abs(self.total_debit - self.total_credit)
    
    def get_accounts_by_type(self, account_type):
        return [item for item in self.real_accounts_data if item['account'].account_type == account_type]

# Buat aplikasi Flask
app = create_app()

# Inisialisasi database
with app.app_context():
    init_database(app)

# ==================== ROUTES ====================
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    background_image = url_for('static', filename='background.jpeg')
    logo_image = url_for('static', filename='logo.png')
    
    return render_template('index.html', 
                         background_image=background_image,
                         logo_image=logo_image)

@app.route('/debug-db')
def debug_db():
    try:
        # Cek koneksi database - PAKAI text() wrapper
        result = db.session.execute(text('SELECT version()')).fetchone()
        db_version = result[0] if result else 'No version'
        
        # Hitung jumlah data di setiap tabel
        user_count = User.query.count()
        account_count = Account.query.count()
        transaction_count = Transaction.query.count()
        journal_count = JournalEntry.query.count()
        adjusting_count = AdjustingEntry.query.count()
        closing_count = ClosingEntry.query.count()
        
        # Ambil beberapa sample data
        users = User.query.limit(5).all()
        accounts = Account.query.limit(5).all()
        transactions = Transaction.query.limit(5).all()
        
        return jsonify({
            'database_connected': True,
            'db_version': db_version,
            'counts': {
                'users': user_count,
                'accounts': account_count,
                'transactions': transaction_count,
                'journal_entries': journal_count,
                'adjusting_entries': adjusting_count,
                'closing_entries': closing_count
            },
            'sample_users': [{'id': u.id, 'username': u.username, 'email': u.email} for u in users],
            'sample_accounts': [{'id': a.id, 'code': a.account_code, 'name': a.account_name, 'type': a.account_type} for a in accounts],
            'sample_transactions': [{'id': t.id, 'date': t.date.strftime('%Y-%m-%d'), 'description': t.description, 'amount': t.amount} for t in transactions]
        })
        
    except Exception as e:
        return jsonify({
            'database_connected': False,
            'error': str(e)
        }), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            flash('Login berhasil! Selamat datang di Tandur Bawang.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username atau password salah!', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        errors = []
        
        if not username or not email or not password:
            errors.append('Semua field harus diisi!')
        
        if User.query.filter_by(username=username).first():
            errors.append('Username sudah ada!')
        
        if User.query.filter_by(email=email).first():
            errors.append('Email sudah terdaftar!')
        
        if len(password) < 6:
            errors.append('Password harus minimal 6 karakter!')
            
        if errors:
            return render_template('register.html', errors=errors)
        
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# API ROUTES FOR DASHBOARD
@app.route('/api/dashboard/financial_data')
@login_required
def dashboard_financial_data():
    try:
        trial_balance_obj = TrialBalance(include_adjusting=True)
        
        ledger_processor = LedgerProcessor(current_user.id)
        
        accounts = Account.query.filter_by(is_active=True).all()
        
        for account in accounts:
            balance = ledger_processor.get_account_balance(account.account_code, 
                                                          include_adjusting=True,
                                                          include_closing=False)
            
            if account.normal_balance == 'Debit':
                if balance >= 0:
                    trial_balance_obj.add_account_balance(account, abs(balance), 0)
                else:
                    trial_balance_obj.add_account_balance(account, 0, abs(balance))
            else:
                if balance >= 0:
                    trial_balance_obj.add_account_balance(account, 0, abs(balance))
                else:
                    trial_balance_obj.add_account_balance(account, abs(balance), 0)
        
        financial_stmt = FinancialStatement()
        income_stmt = financial_stmt.calculate_income_statement(trial_balance_obj)
        balance_sheet = financial_stmt.calculate_balance_sheet(trial_balance_obj, income_stmt['net_income'])
        
        return jsonify({
            'success': True,
            'income_statement': income_stmt,
            'balance_sheet': balance_sheet,
            'net_income': income_stmt['net_income']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/dashboard')
@login_required
def dashboard():
    total_accounts = Account.query.filter_by(is_active=True).count()
    total_transactions = Transaction.query.filter_by(created_by=current_user.id).count()
    total_journal_entries = JournalEntry.query.filter_by(created_by=current_user.id).count()
    
    recent_transactions = Transaction.query.filter_by(created_by=current_user.id).order_by(Transaction.created_at.desc()).limit(5).all()
    
    income_statement = None
    balance_sheet = None
    net_income = 0
    
    try:
        trial_balance_obj = TrialBalance(include_adjusting=True)
        ledger_processor = LedgerProcessor(current_user.id)
        
        accounts = Account.query.filter_by(is_active=True).all()
        
        for account in accounts:
            balance = ledger_processor.get_account_balance(account.account_code, 
                                                          include_adjusting=True,
                                                          include_closing=False)
            
            if account.normal_balance == 'Debit':
                if balance >= 0:
                    trial_balance_obj.add_account_balance(account, abs(balance), 0)
                else:
                    trial_balance_obj.add_account_balance(account, 0, abs(balance))
            else:
                if balance >= 0:
                    trial_balance_obj.add_account_balance(account, 0, abs(balance))
                else:
                    trial_balance_obj.add_account_balance(account, abs(balance), 0)
        
        financial_stmt = FinancialStatement()
        income_statement = financial_stmt.calculate_income_statement(trial_balance_obj)
        balance_sheet = financial_stmt.calculate_balance_sheet(trial_balance_obj, income_statement['net_income'])
        net_income = income_statement['net_income']
        
    except Exception as e:
        print(f"Error calculating financial data: {e}")
    
    logo_image = url_for('static', filename='logo.png')
    
    return render_template('dashboard.html', 
                         total_accounts=total_accounts,
                         total_transactions=total_transactions,
                         total_journal_entries=total_journal_entries,
                         recent_transactions=recent_transactions,
                         income_statement=income_statement,
                         balance_sheet=balance_sheet,
                         net_income=net_income,
                         logo_image=logo_image)

# CHART OF ACCOUNTS ROUTES
@app.route('/chart_of_accounts')
@login_required
def chart_of_accounts():
    accounts = Account.query.filter_by(is_active=True).order_by(Account.account_code).all()
    return render_template('ChartOfAccounts.html', accounts=accounts)

@app.route('/add_account', methods=['POST'])
@login_required
def add_account():
    try:
        account_code = request.form.get('account_code')
        account_name = request.form.get('account_name')
        account_type = request.form.get('account_type')
        category = request.form.get('category')
        normal_balance = request.form.get('normal_balance')
        description = request.form.get('description')
        
        if not all([account_code, account_name, account_type, category, normal_balance]):
            return jsonify({'success': False, 'message': 'Semua field bertanda * harus diisi!'})
        
        if Account.query.filter_by(account_code=account_code).first():
            return jsonify({'success': False, 'message': 'Kode akun sudah ada!'})
        
        new_account = Account(
            account_code=account_code,
            account_name=account_name,
            account_type=account_type,
            category=category,
            normal_balance=normal_balance,
            description=description,
            is_active=True
        )
        
        db.session.add(new_account)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Akun berhasil ditambahkan!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Gagal menambahkan akun: {str(e)}'})

@app.route('/edit_account', methods=['POST'])
@login_required
def edit_account():
    try:
        account_id = request.form.get('account_id')
        account = Account.query.get_or_404(account_id)
        
        account_code = request.form.get('account_code')
        account_name = request.form.get('account_name')
        account_type = request.form.get('account_type')
        category = request.form.get('category')
        normal_balance = request.form.get('normal_balance')
        description = request.form.get('description')
        
        if not all([account_code, account_name, account_type, category, normal_balance]):
            return jsonify({'success': False, 'message': 'Semua field bertanda * harus diisi!'})
        
        existing_account = Account.query.filter_by(account_code=account_code).first()
        if existing_account and existing_account.id != account.id:
            return jsonify({'success': False, 'message': 'Kode akun sudah digunakan oleh akun lain!'})
        
        account.account_code = account_code
        account.account_name = account_name
        account.account_type = account_type
        account.category = category
        account.normal_balance = normal_balance
        account.description = description
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Akun berhasil diperbarui!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Gagal memperbarui akun: {str(e)}'})

@app.route('/accounts/<int:account_id>/edit')
@login_required
def get_account(account_id):
    account = Account.query.get_or_404(account_id)
    return jsonify(account.to_dict())

@app.route('/accounts/<int:account_id>/toggle', methods=['POST'])
@login_required
def toggle_account(account_id):
    try:
        account = Account.query.get_or_404(account_id)
        account.is_active = not account.is_active
        db.session.commit()
        
        action = "diaktifkan" if account.is_active else "dinonaktifkan"
        return jsonify({
            'success': True, 
            'is_active': account.is_active,
            'message': f'Akun {account.account_name} berhasil {action}'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/initialize_default_accounts', methods=['POST'])
@login_required
def initialize_default_accounts():
    try:
        # Hapus semua akun yang ada
        Account.query.delete()
        db.session.commit()
        
        specific_accounts = [
            {'code': '1101', 'name': 'Kas', 'type': 'Aset', 'category': 'Kas & Bank', 'normal_balance': 'Debit'},
            {'code': '1201', 'name': 'Persediaan', 'type': 'Aset', 'category': 'Persediaan', 'normal_balance': 'Debit'},
            {'code': '1301', 'name': 'Peralatan', 'type': 'Aset', 'category': 'Aktiva Tetap', 'normal_balance': 'Debit'},
            {'code': '1311', 'name': 'Akumulasi Penyusutan', 'type': 'Aset Kontra', 'category': 'Aktiva Tetap', 'normal_balance': 'Kredit'},
            {'code': '2101', 'name': 'Utang Usaha', 'type': 'Liabilitas', 'category': 'Utang Lancar', 'normal_balance': 'Kredit'},
            {'code': '2102', 'name': 'Utang Bank', 'type': 'Liabilitas', 'category': 'Utang Jangka Panjang', 'normal_balance': 'Kredit'},
            {'code': '3101', 'name': 'Modal Disetor', 'type': 'Ekuitas', 'category': 'Modal', 'normal_balance': 'Kredit'},
            {'code': '3102', 'name': 'Prive', 'type': 'Ekuitas', 'category': 'Modal', 'normal_balance': 'Debit'},
            {'code': '3901', 'name': 'Ikhtisar Laba Rugi', 'type': 'Ekuitas', 'category': 'Laba Rugi', 'normal_balance': 'Kredit'},
            {'code': '4101', 'name': 'Penjualan', 'type': 'Pendapatan', 'category': 'Pendapatan Usaha', 'normal_balance': 'Kredit'},
            {'code': '4102', 'name': 'Penjualan Lain-lain', 'type': 'Pendapatan', 'category': 'Pendapatan Lain', 'normal_balance': 'Kredit'},
            {'code': '5101', 'name': 'Pembelian', 'type': 'Beban', 'category': 'Harga Pokok', 'normal_balance': 'Debit'},
            {'code': '5901', 'name': 'HPP', 'type': 'Beban', 'category': 'Harga Pokok', 'normal_balance': 'Debit'},
            {'code': '5201', 'name': 'Beban Transportasi', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
            {'code': '5202', 'name': 'Beban Tenaga Kerja', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
            {'code': '5203', 'name': 'Beban Sewa', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
            {'code': '5204', 'name': 'Beban Perbaikan', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
            {'code': '5205', 'name': 'Beban Listrik dan Air', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
            {'code': '5206', 'name': 'Beban Administrasi', 'type': 'Beban', 'category': 'Beban Operasional', 'normal_balance': 'Debit'},
            {'code': '5301', 'name': 'Beban Penyusutan', 'type': 'Beban', 'category': 'Beban Non-Operasional', 'normal_balance': 'Debit'}
        ]
        
        for account_data in specific_accounts:
            account = Account(
                account_code=account_data['code'],
                account_name=account_data['name'],
                account_type=account_data['type'],
                category=account_data['category'],
                normal_balance=account_data['normal_balance'],
                is_active=True
            )
            db.session.add(account)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Akun default berhasil diinisialisasi ulang!'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Gagal menginisialisasi akun: {str(e)}'})

# TRANSACTIONS ROUTES
@app.route('/transactions', methods=['GET', 'POST'])
@login_required
def transactions():
    if request.method == 'POST':
        try:
            date = request.form.get('date')
            description = request.form.get('description')
            account_debit = request.form.get('account_debit')
            account_credit = request.form.get('account_credit')
            amount = request.form.get('amount')
            reference = request.form.get('reference', '')
            
            # Validasi
            if not all([date, description, account_debit, account_credit, amount]):
                flash('Semua field harus diisi!', 'error')
                return redirect(url_for('transactions'))
            
            amount = float(amount)
            if amount <= 0:
                flash('Jumlah harus lebih dari 0!', 'error')
                return redirect(url_for('transactions'))
            
            if account_debit == account_credit:
                flash('Akun debit dan kredit tidak boleh sama!', 'error')
                return redirect(url_for('transactions'))
            
            # Cek akun
            debit_account = Account.query.filter_by(account_code=account_debit).first()
            credit_account = Account.query.filter_by(account_code=account_credit).first()
            
            if not debit_account or not credit_account:
                flash('Akun debit atau kredit tidak valid!', 'error')
                return redirect(url_for('transactions'))
            
            if not debit_account.is_active or not credit_account.is_active:
                flash('Akun tidak aktif!', 'error')
                return redirect(url_for('transactions'))
            
            # Generate transaction number
            transaction_count = Transaction.query.filter_by(created_by=current_user.id).count() + 1
            transaction_number = f"TRX-{datetime.now().strftime('%Y%m%d')}-{transaction_count:04d}"
            
            # Create transaction
            new_transaction = Transaction(
                transaction_number=transaction_number,
                date=datetime.strptime(date, '%Y-%m-%d'),
                description=description,
                account_debit=account_debit,
                account_debit_name=debit_account.account_name,
                account_credit=account_credit,
                account_credit_name=credit_account.account_name,
                amount=amount,
                reference=reference,
                created_by=current_user.id
            )
            
            db.session.add(new_transaction)
            db.session.flush()  # Get the transaction ID
            
            # Create journal entries
            debit_entry = JournalEntry(
                date=new_transaction.date,
                description=description,
                account_code=account_debit,
                account_name=debit_account.account_name,
                debit=amount,
                credit=0,
                reference=transaction_number,
                transaction_id=new_transaction.id,
                created_by=current_user.id,
                entry_type='regular',
                ledger_processed=True,
                ledger_date=datetime.now()
            )
            
            credit_entry = JournalEntry(
                date=new_transaction.date,
                description=description,
                account_code=account_credit,
                account_name=credit_account.account_name,
                debit=0,
                credit=amount,
                reference=transaction_number,
                transaction_id=new_transaction.id,
                created_by=current_user.id,
                entry_type='regular',
                ledger_processed=True,
                ledger_date=datetime.now()
            )
            
            db.session.add(debit_entry)
            db.session.add(credit_entry)
            db.session.commit()
            
            flash('Transaksi berhasil ditambahkan dan diproses ke ledger!', 'success')
            return redirect(url_for('transactions'))
            
        except ValueError:
            flash('Jumlah harus berupa angka!', 'error')
            return redirect(url_for('transactions'))
        except Exception as e:
            db.session.rollback()
            flash(f'Gagal menambahkan transaksi: {str(e)}', 'error')
            return redirect(url_for('transactions'))
    
    # GET request - show transactions
    accounts = Account.query.filter_by(is_active=True).order_by(Account.account_code).all()
    
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    account_filter = request.args.get('account')
    
    query = Transaction.query.filter_by(created_by=current_user.id)
    
    if start_date:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        query = query.filter(Transaction.date >= start_date_obj)
    
    if end_date:
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        query = query.filter(Transaction.date <= end_date_obj)
    
    if account_filter:
        query = query.filter(
            (Transaction.account_debit == account_filter) | 
            (Transaction.account_credit == account_filter)
        )
    
    transactions_list = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    
    total_amount = sum(transaction.amount for transaction in transactions_list)
    
    return render_template('transactions.html',
                         accounts=accounts,
                         transactions=transactions_list,
                         total_amount=total_amount,
                         today=datetime.now().strftime('%Y-%m-%d'),
                         start_date=start_date,
                         end_date=end_date,
                         selected_account=account_filter)

@app.route('/transactions/delete/<int:id>', methods=['POST'])
@login_required
def delete_transaction(id):
    try:
        transaction = Transaction.query.get_or_404(id)
        
        if transaction.created_by != current_user.id:
            flash('Anda tidak memiliki izin untuk menghapus transaksi ini!', 'error')
            return redirect(url_for('transactions'))
        
        # Delete associated journal entries
        JournalEntry.query.filter_by(transaction_id=id).delete()
        
        db.session.delete(transaction)
        db.session.commit()
        
        flash('Transaksi berhasil dihapus!', 'success')
        return redirect(url_for('transactions'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Gagal menghapus transaksi: {str(e)}', 'error')
        return redirect(url_for('transactions'))

# JOURNAL ROUTES
@app.route('/general_journal')
@login_required
def general_journal():
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    account_filter = request.args.get('account')
    entry_type_filter = request.args.get('entry_type')
    
    # Build query
    query = JournalEntry.query.filter_by(created_by=current_user.id)
    
    if start_date:
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        query = query.filter(JournalEntry.date >= start_date_obj)
    
    if end_date:
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        query = query.filter(JournalEntry.date <= end_date_obj)
    
    if account_filter:
        query = query.filter_by(account_code=account_filter)
    
    if entry_type_filter and entry_type_filter != 'all':
        query = query.filter_by(entry_type=entry_type_filter)
    
    # Get all journal entries
    all_entries = query.order_by(JournalEntry.date, JournalEntry.id).all()
    
    # Calculate totals
    total_debit = sum(entry.debit for entry in all_entries)
    total_credit = sum(entry.credit for entry in all_entries)
    
    # Get accounts for dropdown
    accounts = Account.query.filter_by(is_active=True).order_by(Account.account_code).all()
    
    # Get entry types
    entry_types = ['regular', 'adjusting', 'closing']
    
    return render_template('general_journal.html',
                         journal_entries=all_entries,
                         accounts=accounts,
                         entry_types=entry_types,
                         total_debit=total_debit,
                         total_credit=total_credit,
                         start_date=start_date,
                         end_date=end_date,
                         selected_account=account_filter,
                         selected_entry_type=entry_type_filter)

# LEDGER ROUTES
@app.route('/general_ledger')
@login_required
def general_ledger():
    account_id = request.args.get('account_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    selected_account = None
    ledger_data = None
    
    ledger_processor = LedgerProcessor(current_user.id)
    
    accounts = Account.query.filter_by(is_active=True).order_by(Account.account_code).all()
    
    if account_id:
        selected_account = Account.query.get(account_id)
        if selected_account:
            ledger_data = ledger_processor.get_ledger_entries(
                account_code=selected_account.account_code,
                start_date=start_date,
                end_date=end_date,
                include_adjusting=True,
                include_closing=True
            )
    
    return render_template('general_ledger.html',
                         accounts=accounts,
                         selected_account=selected_account,
                         ledger_data=ledger_data,
                         start_date=start_date,
                         end_date=end_date)

# TRIAL BALANCE ROUTES
@app.route('/trial_balance')
@login_required
def trial_balance():
    # Get filter parameters
    date_filter = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
    except ValueError:
        filter_date = datetime.now()
    
    trial_balance_obj = TrialBalance(period=filter_date.strftime('%B %Y'), 
                                    include_adjusting=False, 
                                    include_closing=False)
    
    ledger_processor = LedgerProcessor(current_user.id)
    
    accounts = Account.query.filter_by(is_active=True).all()
    
    for account in accounts:
        # Get balance up to the filter date
        balance = 0
        entries = ledger_processor.get_ledger_entries(
            account_code=account.account_code,
            end_date=filter_date,
            include_adjusting=False,
            include_closing=False
        )
        
        if entries:
            balance = entries[-1]['running_balance'] if entries else 0
        
        if account.normal_balance == 'Debit':
            if balance >= 0:
                trial_balance_obj.add_account_balance(account, abs(balance), 0)
            else:
                trial_balance_obj.add_account_balance(account, 0, abs(balance))
        else:
            if balance >= 0:
                trial_balance_obj.add_account_balance(account, 0, abs(balance))
            else:
                trial_balance_obj.add_account_balance(account, abs(balance), 0)
    
    printed_date = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    return render_template('trial_balance.html',
                         trial_balance=trial_balance_obj,
                         period=trial_balance_obj.period,
                         printed_date=printed_date,
                         filter_date=date_filter)

# ADJUSTED TRIAL BALANCE ROUTES
@app.route('/adjusted_trial_balance')
@login_required
def adjusted_trial_balance():
    # Get filter parameters
    date_filter = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
    except ValueError:
        filter_date = datetime.now()
    
    trial_balance_obj = TrialBalance(period=filter_date.strftime('%B %Y'), 
                                    include_adjusting=True, 
                                    include_closing=False)
    
    ledger_processor = LedgerProcessor(current_user.id)
    
    accounts = Account.query.filter_by(is_active=True).all()
    
    for account in accounts:
        # Get balance up to the filter date including adjusting entries
        balance = 0
        entries = ledger_processor.get_ledger_entries(
            account_code=account.account_code,
            end_date=filter_date,
            include_adjusting=True,
            include_closing=False
        )
        
        if entries:
            balance = entries[-1]['running_balance'] if entries else 0
        
        if account.normal_balance == 'Debit':
            if balance >= 0:
                trial_balance_obj.add_account_balance(account, abs(balance), 0)
            else:
                trial_balance_obj.add_account_balance(account, 0, abs(balance))
        else:
            if balance >= 0:
                trial_balance_obj.add_account_balance(account, 0, abs(balance))
            else:
                trial_balance_obj.add_account_balance(account, abs(balance), 0)
    
    printed_date = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    return render_template('adjusted_trial_balance.html',
                         trial_balance=trial_balance_obj,
                         period=trial_balance_obj.period,
                         printed_date=printed_date,
                         filter_date=date_filter)

# ADJUSTING ENTRIES ROUTES
@app.route('/adjusting_entries')
@login_required
def adjusting_entries():
    adjusting_entries = AdjustingEntry.query.filter_by(created_by=current_user.id)\
        .order_by(AdjustingEntry.date.desc(), AdjustingEntry.id.desc()).all()
    
    total_debit = sum(entry.amount for entry in adjusting_entries)
    total_credit = total_debit
    
    accounts = Account.query.filter_by(is_active=True).order_by(Account.account_code).all()
    
    return render_template('adjusting_entries.html',
                         adjusting_entries=adjusting_entries,
                         total_debit=total_debit,
                         total_credit=total_credit,
                         accounts=accounts,
                         current_date=datetime.now().strftime('%Y-%m-%d'))

@app.route('/add_adjusting_entry', methods=['POST'])
@login_required
def add_adjusting_entry():
    try:
        date = request.form['date']
        account_debit_code = request.form['account_debit_code']
        account_credit_code = request.form['account_credit_code']
        amount = float(request.form['amount'])
        description = request.form.get('description', '').strip()
        adjustment_type = request.form.get('adjustment_type', '')
        
        if account_debit_code == account_credit_code:
            flash('Akun debit dan kredit tidak boleh sama!', 'error')
            return redirect(url_for('adjusting_entries'))
        
        reference = f"ADJ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        
        debit_account = Account.query.filter_by(account_code=account_debit_code).first()
        credit_account = Account.query.filter_by(account_code=account_credit_code).first()
        
        if not debit_account or not credit_account:
            flash('Kode akun tidak valid', 'error')
            return redirect(url_for('adjusting_entries'))
        
        if not description:
            description = f"Penyesuaian: {debit_account.account_name} dan {credit_account.account_name}"
        
        new_entry = AdjustingEntry(
            date=datetime.strptime(date, '%Y-%m-%d'),
            reference=reference,
            description=description,
            adjustment_type=adjustment_type,
            account_debit_code=account_debit_code,
            account_debit_name=debit_account.account_name,
            account_credit_code=account_credit_code,
            account_credit_name=credit_account.account_name,
            amount=amount,
            created_by=current_user.id,
            posted_to_ledger=True
        )
        
        db.session.add(new_entry)
        db.session.flush()  # Get the entry ID
        
        # Create journal entries
        debit_journal = JournalEntry(
            date=datetime.strptime(date, '%Y-%m-%d'),
            description=description,
            account_code=account_debit_code,
            account_name=debit_account.account_name,
            debit=amount,
            credit=0.0,
            reference=reference,
            adjusting_entry_id=new_entry.id,
            created_by=current_user.id,
            entry_type='adjusting',
            ledger_processed=True,
            ledger_date=datetime.now()
        )
        
        credit_journal = JournalEntry(
            date=datetime.strptime(date, '%Y-%m-%d'),
            description=description,
            account_code=account_credit_code,
            account_name=credit_account.account_name,
            debit=0.0,
            credit=amount,
            reference=reference,
            adjusting_entry_id=new_entry.id,
            created_by=current_user.id,
            entry_type='adjusting',
            ledger_processed=True,
            ledger_date=datetime.now()
        )
        
        db.session.add(debit_journal)
        db.session.add(credit_journal)
        
        db.session.commit()
        flash('Jurnal penyesuaian berhasil ditambahkan!', 'success')
        return redirect(url_for('adjusting_entries'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('adjusting_entries'))

@app.route('/adjusting_entries/delete/<int:id>', methods=['POST'])
@login_required
def delete_adjusting_entry(id):
    try:
        entry = AdjustingEntry.query.get_or_404(id)
        
        if entry.created_by != current_user.id:
            flash('Anda tidak memiliki izin untuk menghapus entri ini!', 'error')
            return redirect(url_for('adjusting_entries'))
        
        # Delete associated journal entries
        JournalEntry.query.filter_by(adjusting_entry_id=id).delete()
        
        db.session.delete(entry)
        db.session.commit()
        
        flash('Jurnal penyesuaian berhasil dihapus dari semua sistem!', 'success')
        return redirect(url_for('adjusting_entries'))
        
    except Exception as e:
        db.session.rollback()
        flash('Gagal menghapus jurnal penyesuaian: ' + str(e), 'error')
        return redirect(url_for('adjusting_entries'))

# FINANCIAL STATEMENTS ROUTES
@app.route('/financial_statements')
@login_required
def financial_statements():
    # Get period parameter
    period_filter = request.args.get('period', datetime.now().strftime('%Y-%m'))
    
    try:
        filter_date = datetime.strptime(period_filter + '-01', '%Y-%m-%d')
    except ValueError:
        filter_date = datetime.now()
    
    period_str = filter_date.strftime('%B %Y')
    
    trial_balance_obj = TrialBalance(period=period_str, 
                                    include_adjusting=True, 
                                    include_closing=False)
    
    ledger_processor = LedgerProcessor(current_user.id)
    
    accounts = Account.query.filter_by(is_active=True).all()
    
    # Calculate end date for the period (end of month)
    if filter_date.month == 12:
        end_date = datetime(filter_date.year + 1, 1, 1)
    else:
        end_date = datetime(filter_date.year, filter_date.month + 1, 1)
    
    for account in accounts:
        # Get balance for the period
        balance = 0
        entries = ledger_processor.get_ledger_entries(
            account_code=account.account_code,
            start_date=filter_date,
            end_date=end_date,
            include_adjusting=True,
            include_closing=False
        )
        
        if entries:
            balance = entries[-1]['running_balance'] if entries else 0
        
        if account.normal_balance == 'Debit':
            if balance >= 0:
                trial_balance_obj.add_account_balance(account, abs(balance), 0)
            else:
                trial_balance_obj.add_account_balance(account, 0, abs(balance))
        else:
            if balance >= 0:
                trial_balance_obj.add_account_balance(account, 0, abs(balance))
            else:
                trial_balance_obj.add_account_balance(account, abs(balance), 0)
    
    financial_stmt = FinancialStatement(period=period_str)
    income_stmt = financial_stmt.calculate_income_statement(trial_balance_obj)
    balance_sheet = financial_stmt.calculate_balance_sheet(trial_balance_obj, income_stmt['net_income'])
    
    return render_template('financial_statements.html',
                         income_statement=income_stmt,
                         balance_sheet=balance_sheet,
                         period=period_str,
                         current_date=datetime.now().strftime('%d/%m/%Y %H:%M'),
                         period_filter=period_filter)

# CLOSING ENTRIES ROUTES
@app.route('/closing_entries')
@login_required
def closing_entries():
    try:
        # Check if we need to generate closing entries
        generate_new = request.args.get('generate', 'false') == 'true'
        
        if generate_new:
            closing_processor = ClosingProcessor(current_user.id)
            closing_entries_list = closing_processor.generate_closing_entries()
            success, message = closing_processor.save_closing_entries()
            
            if success:
                flash('Closing entries berhasil digenerate!', 'success')
            else:
                flash(f'Peringatan: {message}', 'warning')
                
    except Exception as e:
        flash(f'Error dalam generating closing entries: {str(e)}', 'error')
    
    # Get existing entries
    existing_entries = ClosingEntry.query.filter_by(created_by=current_user.id)\
        .order_by(ClosingEntry.date.desc(), ClosingEntry.id.desc()).all()
    
    total_debit = sum(entry.amount for entry in existing_entries)
    total_credit = total_debit
    
    # Calculate closure percentage
    nominal_accounts = Account.query.filter(Account.account_type.in_(['Pendapatan', 'Beban'])).all()
    closed_nominal_count = 0
    
    for account in nominal_accounts:
        if any(entry.account_debit_code == account.account_code or 
               entry.account_credit_code == account.account_code 
               for entry in existing_entries):
            closed_nominal_count += 1
    
    nominal_accounts_closed = closed_nominal_count == len(nominal_accounts)
    closure_percentage = round((closed_nominal_count / len(nominal_accounts)) * 100) if nominal_accounts else 0
    
    return render_template('closing_entries.html',
                         closing_entries=existing_entries,
                         total_debit=total_debit,
                         total_credit=total_credit,
                         nominal_accounts_closed=nominal_accounts_closed,
                         closure_percentage=closure_percentage,
                         current_date=datetime.now())

@app.route('/generate-closing-entries', methods=['POST'])
@login_required
def generate_closing_entries():
    try:
        closing_processor = ClosingProcessor(current_user.id)
        closing_entries_list = closing_processor.generate_closing_entries()
        success, message = closing_processor.save_closing_entries()
        
        if success:
            return jsonify({
                'success': True,
                'message': message,
                'entries_count': len(closing_entries_list)
            })
        else:
            return jsonify({
                'success': False,
                'message': message
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Gagal generate closing entries: {str(e)}'
        }), 500

# POST-CLOSING TRIAL BALANCE ROUTES
@app.route('/post_closing_trial_balance')
@login_required
def post_closing_trial_balance():
    # Get filter parameters
    date_filter = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    try:
        filter_date = datetime.strptime(date_filter, '%Y-%m-%d')
    except ValueError:
        filter_date = datetime.now()
    
    period_str = filter_date.strftime('%B %Y')
    
    ledger_processor = LedgerProcessor(current_user.id)
    
    # Get all real accounts (Assets, Liabilities, Equity)
    real_accounts = Account.query.filter(
        Account.account_type.in_(['Aset', 'Liabilitas', 'Ekuitas']),
        Account.is_active == True
    ).order_by(Account.account_code).all()
    
    trial_balance_data = []
    total_debit = 0
    total_credit = 0
    
    for account in real_accounts:
        # Get balance including closing entries
        balance = 0
        entries = ledger_processor.get_ledger_entries(
            account_code=account.account_code,
            end_date=filter_date,
            include_adjusting=True,
            include_closing=True
        )
        
        if entries:
            balance = entries[-1]['running_balance'] if entries else 0
        
        if account.normal_balance == 'Debit':
            if balance >= 0:
                trial_balance_data.append({
                    'account': account,
                    'debit': abs(balance),
                    'credit': 0
                })
                total_debit += abs(balance)
            else:
                trial_balance_data.append({
                    'account': account,
                    'debit': 0,
                    'credit': abs(balance)
                })
                total_credit += abs(balance)
        else:
            if balance >= 0:
                trial_balance_data.append({
                    'account': account,
                    'debit': 0,
                    'credit': abs(balance)
                })
                total_credit += abs(balance)
            else:
                trial_balance_data.append({
                    'account': account,
                    'debit': abs(balance),
                    'credit': 0
                })
                total_debit += abs(balance)
    
    printed_date = datetime.now().strftime('%d/%m/%Y %H:%M')
    
    return render_template('post_closing_trial_balance.html',
                         trial_balance_data=trial_balance_data,
                         total_debit=total_debit,
                         total_credit=total_credit,
                         period=period_str,
                         printed_date=printed_date,
                         filter_date=date_filter)

# DATA EXPORT ROUTES
@app.route('/export_data')
@login_required
def export_data():
    """Export all accounting data"""
    try:
        # Create a CSV file in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Data Type', 'ID', 'Date', 'Description', 'Account Code', 
                        'Account Name', 'Debit', 'Credit', 'Reference', 'Entry Type'])
        
        # Get all journal entries
        journal_entries = JournalEntry.query.filter_by(created_by=current_user.id)\
            .order_by(JournalEntry.date, JournalEntry.id).all()
        
        for entry in journal_entries:
            writer.writerow([
                'Journal Entry',
                entry.id,
                entry.date.strftime('%Y-%m-%d'),
                entry.description,
                entry.account_code,
                entry.account_name,
                entry.debit,
                entry.credit,
                entry.reference,
                entry.entry_type
            ])
        
        # Get all transactions
        transactions = Transaction.query.filter_by(created_by=current_user.id)\
            .order_by(Transaction.date, Transaction.id).all()
        
        for trx in transactions:
            writer.writerow([
                'Transaction',
                trx.id,
                trx.date.strftime('%Y-%m-%d'),
                trx.description,
                f"{trx.account_debit}/{trx.account_credit}",
                f"{trx.account_debit_name}/{trx.account_credit_name}",
                trx.amount,
                trx.amount,
                trx.reference,
                'regular'
            ])
        
        # Get all adjusting entries
        adjusting_entries = AdjustingEntry.query.filter_by(created_by=current_user.id).all()
        
        for adj in adjusting_entries:
            writer.writerow([
                'Adjusting Entry',
                adj.id,
                adj.date.strftime('%Y-%m-%d'),
                adj.description,
                f"{adj.account_debit_code}/{adj.account_credit_code}",
                f"{adj.account_debit_name}/{adj.account_credit_name}",
                adj.amount,
                adj.amount,
                adj.reference,
                'adjusting'
            ])
        
        # Get all closing entries
        closing_entries = ClosingEntry.query.filter_by(created_by=current_user.id).all()
        
        for cls in closing_entries:
            writer.writerow([
                'Closing Entry',
                cls.id,
                cls.date.strftime('%Y-%m-%d'),
                cls.description,
                f"{cls.account_debit_code}/{cls.account_credit_code}",
                f"{cls.account_debit_name}/{cls.account_credit_name}",
                cls.amount,
                cls.amount,
                cls.reference,
                'closing'
            ])
        
        # Prepare the output
        output.seek(0)
        
        # Create response
        response = send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'accounting_data_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
        )
        
        return response
        
    except Exception as e:
        flash(f'Gagal mengekspor data: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/reset_data', methods=['POST'])
@login_required
def reset_data():
    """Reset all accounting data (except accounts)"""
    try:
        # Delete all transactions and related entries
        Transaction.query.filter_by(created_by=current_user.id).delete()
        JournalEntry.query.filter_by(created_by=current_user.id).delete()
        AdjustingEntry.query.filter_by(created_by=current_user.id).delete()
        ClosingEntry.query.filter_by(created_by=current_user.id).delete()
        
        db.session.commit()
        
        flash('Semua data transaksi berhasil direset! Akun Chart of Accounts tetap tersimpan.', 'success')
        return jsonify({'success': True, 'message': 'Data berhasil direset'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Gagal mereset data: {str(e)}'}), 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('index'))

@app.route('/test-db')
def test_db():
    try:
        db.session.execute(text('SELECT 1'))
        return "Database connection OK"
    except Exception as e:
        return f"Database error: {str(e)}"

# ERROR HANDLERS
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Untuk Render, pakai PORT dari environment variable
    port = int(os.environ.get('PORT', 10000))
    
    # Debug mode hanya untuk local, di Render harus False
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(
        host='0.0.0.0',  # Wajib untuk Render
        port=port,
        debug=debug_mode
    )
