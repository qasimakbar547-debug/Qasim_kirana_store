from pathlib import Path
import sqlite3
from datetime import date, timedelta
import pandas as pd
import streamlit as st

# Qasim Smart Kirana Store Manager
# Existing database is preserved. This app never drops or resets tables.
DB_PATH = Path(__file__).with_name('kirana.db')

st.set_page_config(page_title='Qasim Smart Kirana', page_icon='🛒', layout='wide', initial_sidebar_state='expanded')
st.markdown('''<style>
:root{--ink:#172554;--teal:#0f766e;--muted:#64748b}
.stApp{background:linear-gradient(180deg,#f8fafc 0%,#eef5f7 100%)}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#10243e,#123b50);}
[data-testid="stSidebar"] *{color:#f8fafc!important}
.block-container{padding-top:1.5rem;padding-bottom:2rem;max-width:1450px}
.hero{padding:26px 30px;border-radius:20px;background:linear-gradient(120deg,#10243e,#0f766e);color:white;margin-bottom:20px;box-shadow:0 10px 28px #0f172a18}
.hero h1{font-size:2rem;margin:0 0 8px 0;color:white}.hero p{margin:0;color:#dbeafe}
div[data-testid="stMetric"]{background:white;border:1px solid #e2e8f0;padding:16px 18px;border-radius:16px;box-shadow:0 4px 16px #0f172a08}
.stButton>button{border-radius:10px;font-weight:600;border:0;background:#0f766e;color:white}
.stButton>button:hover{background:#115e59;color:white}
[data-testid="stForm"]{background:white;padding:18px;border:1px solid #e2e8f0;border-radius:16px}
h2,h3{color:#17324d}
</style>''', unsafe_allow_html=True)


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def columns(conn, table):
    return {r['name'] for r in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def initialize_database():
    with get_connection() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL DEFAULT 'Qasim Smart Kirana Store',
            owner_name TEXT DEFAULT '', phone TEXT DEFAULT '', address TEXT DEFAULT '', currency TEXT DEFAULT 'Rs'
        )''')
        # Add only missing settings columns; existing rows/data remain untouched.
        existing = columns(conn, 'stores')
        for col, definition in [('owner_name', "TEXT DEFAULT ''"), ('phone', "TEXT DEFAULT ''"), ('address', "TEXT DEFAULT ''"), ('currency', "TEXT DEFAULT 'Rs'")]:
            if col not in existing:
                conn.execute(f'ALTER TABLE stores ADD COLUMN {col} {definition}')
        conn.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, store_id INTEGER NOT NULL,
            name TEXT NOT NULL, category TEXT DEFAULT '', barcode TEXT DEFAULT '',
            purchase_price REAL NOT NULL DEFAULT 0, sale_price REAL NOT NULL DEFAULT 0,
            quantity REAL NOT NULL DEFAULT 0, low_stock_limit REAL NOT NULL DEFAULT 5,
            unit TEXT DEFAULT 'pcs', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(store_id) REFERENCES stores(id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, store_id INTEGER NOT NULL,
            name TEXT NOT NULL, phone TEXT DEFAULT '', address TEXT DEFAULT '',
            balance REAL NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(store_id) REFERENCES stores(id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT, store_id INTEGER NOT NULL,
            customer_id INTEGER, total REAL NOT NULL DEFAULT 0, paid REAL NOT NULL DEFAULT 0,
            date TEXT DEFAULT CURRENT_TIMESTAMP, notes TEXT DEFAULT '',
            FOREIGN KEY(store_id) REFERENCES stores(id), FOREIGN KEY(customer_id) REFERENCES customers(id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
            quantity REAL NOT NULL, unit_price REAL NOT NULL, unit_cost REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(sale_id) REFERENCES sales(id), FOREIGN KEY(product_id) REFERENCES products(id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, store_id INTEGER NOT NULL, product_id INTEGER NOT NULL,
            quantity REAL NOT NULL, unit_cost REAL NOT NULL, total REAL NOT NULL,
            supplier TEXT DEFAULT '', date TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(store_id) REFERENCES stores(id), FOREIGN KEY(product_id) REFERENCES products(id))''')
        if conn.execute('SELECT COUNT(*) FROM stores').fetchone()[0] == 0:
            conn.execute("INSERT INTO stores(name) VALUES ('Qasim Smart Kirana Store')")
        # Compatibility for older database schemas: rename common legacy column
        # names to the names used by this app. RENAME COLUMN preserves all row data.
        # Do this before adding missing columns or running any page queries.
        legacy_aliases = {
            'products': {
                'name': ('product_name', 'item_name', 'product', 'item'),
                'quantity': ('stock', 'stock_quantity', 'qty', 'current_stock'),
                'purchase_price': ('cost_price', 'buying_price', 'unit_cost'),
                'sale_price': ('selling_price', 'retail_price', 'unit_price'),
                'low_stock_limit': ('low_stock', 'reorder_level', 'alert_at'),
                'unit': ('unit_name',),
            },
            'customers': {
                'name': ('customer_name', 'full_name'),
                'balance': ('udhaar', 'due', 'outstanding_balance'),
            },
            'purchases': {
                'quantity': ('qty', 'purchase_quantity', 'quantity_purchased', 'stock_in'),
                'unit_cost': ('cost_price', 'purchase_price', 'price_per_unit'),
                'total': ('amount', 'total_amount', 'purchase_total'),
                'supplier': ('supplier_name', 'vendor', 'vendor_name'),
                'date': ('purchase_date', 'created_at', 'date_created'),
                'product_id': ('item_id',),
                'store_id': ('shop_id',),
            },
            'stores': {'name': ('store_name',)},
        }
        for table, aliases in legacy_aliases.items():
            existing_cols = columns(conn, table)
            for target, alternatives in aliases.items():
                if target not in existing_cols:
                    source = next((candidate for candidate in alternatives if candidate in existing_cols), None)
                    if source:
                        conn.execute(f'ALTER TABLE {table} RENAME COLUMN "{source}" TO "{target}"')
                        existing_cols.remove(source)
                        existing_cols.add(target)

        # Ensure legacy tables have the columns this version needs, without dropping anything.
        for table, wanted in {
            'products': [('category', "TEXT DEFAULT ''"), ('barcode', "TEXT DEFAULT ''"), ('purchase_price', 'REAL NOT NULL DEFAULT 0'), ('sale_price', 'REAL NOT NULL DEFAULT 0'), ('quantity', 'REAL NOT NULL DEFAULT 0'), ('low_stock_limit', 'REAL NOT NULL DEFAULT 5'), ('unit', "TEXT DEFAULT 'pcs'"), ('created_at', 'TEXT')],
            'customers': [('phone', "TEXT DEFAULT ''"), ('address', "TEXT DEFAULT ''"), ('balance', 'REAL NOT NULL DEFAULT 0'), ('created_at', 'TEXT')],
            'sales': [('customer_id', 'INTEGER'), ('total', 'REAL NOT NULL DEFAULT 0'), ('paid', 'REAL NOT NULL DEFAULT 0'), ('date', 'TEXT'), ('notes', "TEXT DEFAULT ''")],
            'sale_items': [('unit_cost', 'REAL NOT NULL DEFAULT 0')],
            'purchases': [('store_id', 'INTEGER'), ('product_id', 'INTEGER'), ('quantity', 'REAL NOT NULL DEFAULT 0'), ('unit_cost', 'REAL NOT NULL DEFAULT 0'), ('total', 'REAL NOT NULL DEFAULT 0'), ('supplier', "TEXT DEFAULT ''"), ('date', 'TEXT')]
        }.items():
            existing = columns(conn, table)
            for col, definition in wanted:
                if col not in existing:
                    conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {definition}')
            # SQLite cannot add a column with CURRENT_TIMESTAMP as its default to
            # a populated legacy table. Add it as TEXT, then populate missing values.
            if table == 'products' and 'created_at' in columns(conn, table):
                conn.execute("UPDATE products SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL OR created_at=''")
            elif table == 'customers' and 'created_at' in columns(conn, table):
                conn.execute("UPDATE customers SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL OR created_at=''")
            elif table == 'sales' and 'date' in columns(conn, table):
                conn.execute("UPDATE sales SET date=CURRENT_TIMESTAMP WHERE date IS NULL OR date=''")
            elif table == 'purchases' and 'date' in columns(conn, table):
                conn.execute("UPDATE purchases SET date=CURRENT_TIMESTAMP WHERE date IS NULL OR date=''")

initialize_database()
with get_connection() as conn:
    STORE_ID = conn.execute('SELECT id FROM stores ORDER BY id LIMIT 1').fetchone()['id']


def settings():
    with get_connection() as conn:
        return dict(conn.execute('SELECT * FROM stores WHERE id=?', (STORE_ID,)).fetchone())


def currency():
    return settings().get('currency') or 'Rs'


def money(value):
    try:
        return f"{currency()} {float(value or 0):,.2f}"
    except (ValueError, TypeError):
        return f'{currency()} 0.00'


def query_df(sql, params=()):
    with get_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def product_options():
    return query_df('SELECT id, name, quantity, purchase_price, sale_price, unit FROM products WHERE store_id=? ORDER BY name', (STORE_ID,))


def customer_options():
    return query_df('SELECT id, name, balance FROM customers WHERE store_id=? ORDER BY name', (STORE_ID,))


def heading(title, subtitle=''):
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def save_product(name, category, barcode, cost, price, qty, low, unit):
    with get_connection() as conn:
        conn.execute('INSERT INTO products(store_id,name,category,barcode,purchase_price,sale_price,quantity,low_stock_limit,unit) VALUES(?,?,?,?,?,?,?,?,?)',
                     (STORE_ID, name.strip(), category.strip(), barcode.strip(), cost, price, qty, low, unit))

store = settings()
st.sidebar.markdown('## 🛒 Qasim Smart Kirana')
st.sidebar.caption(store.get('name') or 'Store Manager')
page = st.sidebar.radio('NAVIGATION', ['Dashboard', 'Inventory / Stock', 'Sales & Billing', 'Purchases', 'Customers / Udhaar', 'Reports', 'Settings'])
st.sidebar.divider()
st.sidebar.caption('Inventory • Billing • Accounts')

if page == 'Dashboard':
    heading('Store Dashboard', 'Your daily kirana business at a glance.')
    today = date.today().isoformat()
    with get_connection() as conn:
        product_count = conn.execute('SELECT COUNT(*) FROM products WHERE store_id=?', (STORE_ID,)).fetchone()[0]
        customer_count = conn.execute('SELECT COUNT(*) FROM customers WHERE store_id=?', (STORE_ID,)).fetchone()[0]
        today_sales = conn.execute("SELECT COALESCE(SUM(total),0) FROM sales WHERE store_id=? AND date(date)=date(?)", (STORE_ID, today)).fetchone()[0]
        today_paid = conn.execute("SELECT COALESCE(SUM(paid),0) FROM sales WHERE store_id=? AND date(date)=date(?)", (STORE_ID, today)).fetchone()[0]
        udhaar = conn.execute('SELECT COALESCE(SUM(balance),0) FROM customers WHERE store_id=?', (STORE_ID,)).fetchone()[0]
        stock_value = conn.execute('SELECT COALESCE(SUM(quantity*purchase_price),0) FROM products WHERE store_id=?', (STORE_ID,)).fetchone()[0]
        low_count = conn.execute('SELECT COUNT(*) FROM products WHERE store_id=? AND quantity<=low_stock_limit', (STORE_ID,)).fetchone()[0]
    a,b,c,d = st.columns(4)
    a.metric('Today Sales', money(today_sales)); b.metric('Received Today', money(today_paid)); c.metric('Customers', customer_count); d.metric('Products', product_count)
    a,b,c = st.columns(3)
    a.metric('Customer Udhaar', money(udhaar)); b.metric('Stock Purchase Value', money(stock_value)); c.metric('Low-stock Items', low_count)
    st.subheader('⚠️ Low Stock Alert')
    low = query_df('SELECT name AS Product, quantity AS Stock, low_stock_limit AS "Alert At", unit AS Unit FROM products WHERE store_id=? AND quantity<=low_stock_limit ORDER BY quantity', (STORE_ID,))
    st.dataframe(low, use_container_width=True, hide_index=True)
    st.subheader('Recent Sales')
    recent = query_df('SELECT s.id AS Bill, COALESCE(c.name,\'Walk-in Customer\') AS Customer, s.total AS Total, s.paid AS Paid, (s.total-s.paid) AS Due, s.date AS Date FROM sales s LEFT JOIN customers c ON c.id=s.customer_id WHERE s.store_id=? ORDER BY s.id DESC LIMIT 10', (STORE_ID,))
    st.dataframe(recent, use_container_width=True, hide_index=True)

elif page == 'Inventory / Stock':
    heading('Inventory & Stock', 'Add products, review stock and update selling prices.')
    with st.expander('➕ Add New Product', expanded=True):
        with st.form('product_form', clear_on_submit=True):
            a,b,c = st.columns(3)
            name = a.text_input('Product name *'); category = b.text_input('Category'); barcode = c.text_input('Barcode (optional)')
            a,b,c,d = st.columns(4)
            cost = a.number_input('Purchase price', min_value=0.0, step=1.0); price = b.number_input('Sale price', min_value=0.0, step=1.0)
            qty = c.number_input('Opening stock', min_value=0.0, step=1.0); low = d.number_input('Low stock alert at', min_value=0.0, value=5.0, step=1.0)
            unit = st.selectbox('Unit', ['pcs','kg','g','litre','ml','pack','dozen','box'])
            submitted = st.form_submit_button('Save Product', use_container_width=True)
            if submitted:
                if not name.strip(): st.error('Product name is required.')
                else:
                    save_product(name, category, barcode, cost, price, qty, low, unit); st.success('Product saved.'); st.rerun()
    products = query_df('SELECT id AS ID,name AS Product,category AS Category,barcode AS Barcode,purchase_price AS "Cost Price",sale_price AS "Sale Price",quantity AS Stock,low_stock_limit AS "Low Stock At",unit AS Unit FROM products WHERE store_id=? ORDER BY name', (STORE_ID,))
    st.dataframe(products, use_container_width=True, hide_index=True)
    if not products.empty:
        st.download_button('⬇️ Download Inventory CSV', products.to_csv(index=False).encode('utf-8-sig'), 'inventory.csv', 'text/csv')
        with st.expander('✏️ Adjust Stock / Prices'):
            ids = products['ID'].tolist(); chosen = st.selectbox('Choose product', ids, format_func=lambda x: products.loc[products.ID==x,'Product'].iloc[0])
            current = products[products.ID==chosen].iloc[0]
            with st.form('adjust_form'):
                new_qty = st.number_input('Set current stock', min_value=0.0, value=float(current['Stock']), step=1.0)
                new_cost = st.number_input('Purchase price', min_value=0.0, value=float(current['Cost Price']), step=1.0)
                new_price = st.number_input('Sale price', min_value=0.0, value=float(current['Sale Price']), step=1.0)
                if st.form_submit_button('Update Product'):
                    with get_connection() as conn: conn.execute('UPDATE products SET quantity=?,purchase_price=?,sale_price=? WHERE id=? AND store_id=?', (new_qty,new_cost,new_price,chosen,STORE_ID))
                    st.success('Product updated.'); st.rerun()

elif page == 'Sales & Billing':
    heading('Sales & Billing', 'Create a bill, reduce stock automatically and track udhaar.')
    products = product_options(); customers = customer_options()
    if products.empty: st.warning('Add a product in Inventory / Stock before making a sale.')
    else:
        with st.form('sale_form', clear_on_submit=True):
            options = products.id.tolist()
            pid = st.selectbox('Product', options, format_func=lambda x: f"{products.loc[products.id==x,'name'].iloc[0]} (stock: {products.loc[products.id==x,'quantity'].iloc[0]:g})")
            row = products[products.id==pid].iloc[0]
            qty = st.number_input('Quantity', min_value=0.01, value=1.0, step=1.0)
            price = st.number_input('Unit sale price', min_value=0.0, value=float(row.sale_price), step=1.0)
            cust_choice = st.selectbox('Customer', ['Walk-in / Cash'] + customers.id.tolist(), format_func=lambda x: x if isinstance(x,str) else customers.loc[customers.id==x,'name'].iloc[0])
            paid = st.number_input('Amount received now', min_value=0.0, step=10.0)
            notes = st.text_input('Notes (optional)')
            submit = st.form_submit_button('✅ Complete Sale', use_container_width=True)
            if submit:
                total = qty * price
                if qty > float(row.quantity): st.error('Not enough stock available.')
                elif paid > total: st.error('Received amount cannot exceed bill total.')
                else:
                    cid = None if isinstance(cust_choice,str) else int(cust_choice)
                    with get_connection() as conn:
                        cur = conn.execute('INSERT INTO sales(store_id,customer_id,total,paid,notes) VALUES(?,?,?,?,?)',(STORE_ID,cid,total,paid,notes))
                        sid = cur.lastrowid
                        conn.execute('INSERT INTO sale_items(sale_id,product_id,quantity,unit_price,unit_cost) VALUES(?,?,?,?,?)',(sid,pid,qty,price,float(row.purchase_price)))
                        conn.execute('UPDATE products SET quantity=quantity-? WHERE id=? AND store_id=?',(qty,pid,STORE_ID))
                        if cid is not None and total > paid: conn.execute('UPDATE customers SET balance=balance+? WHERE id=? AND store_id=?',(total-paid,cid,STORE_ID))
                    st.success(f'Bill #{sid} saved. Total: {money(total)} | Due: {money(total-paid)}'); st.rerun()
    st.subheader('Recent Bills')
    st.dataframe(query_df("SELECT s.id AS Bill,COALESCE(c.name,'Walk-in Customer') AS Customer,s.total AS Total,s.paid AS Paid,(s.total-s.paid) AS Due,s.date AS Date FROM sales s LEFT JOIN customers c ON c.id=s.customer_id WHERE s.store_id=? ORDER BY s.id DESC LIMIT 50",(STORE_ID,)), use_container_width=True, hide_index=True)

elif page == 'Purchases':
    heading('Purchases & Stock In', 'Record stock bought from suppliers.')

    products = product_options()

    if products.empty:
        st.warning('First add products in Inventory / Stock.')
    else:
        with st.form('purchase_form', clear_on_submit=True):
            pid = st.selectbox(
                'Product',
                products.id.tolist(),
                format_func=lambda x: products.loc[
                    products.id == x, 'name'
                ].iloc[0]
            )

            row = products[products.id == pid].iloc[0]

            qty = st.number_input(
                'Quantity purchased',
                min_value=0.01,
                value=1.0,
                step=1.0
            )

            cost = st.number_input(
                'Cost per unit',
                min_value=0.0,
                value=float(row.purchase_price),
                step=1.0
            )

            supplier = st.text_input('Supplier name (optional)')

            submitted = st.form_submit_button(
                'Save Purchase',
                use_container_width=True
            )

            if submitted:
                with get_connection() as conn:
                    conn.execute(
                        '''
                        INSERT INTO purchases
                        (store_id, product_id, quantity, unit_cost, total, supplier)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ''',
                        (
                            STORE_ID,
                            pid,
                            qty,
                            cost,
                            qty * cost,
                            supplier
                        )
                    )

                    conn.execute(
                        '''
                        UPDATE products
                        SET quantity = quantity + ?,
                            purchase_price = ?
                        WHERE id = ? AND store_id = ?
                        ''',
                        (qty, cost, pid, STORE_ID)
                    )

                st.success('Purchase recorded and stock updated.')
                st.rerun()

    st.subheader('Purchase History')

    purchases = query_df(
        '''
        SELECT
            p.id AS ID,
            COALESCE(pr.name, 'Unknown product') AS Product,
            p.quantity AS Quantity,
            p.unit_cost AS "Unit Cost",
            p.total AS Total,
            COALESCE(p.supplier, '') AS Supplier,
            p.date AS Date
        FROM purchases p
        LEFT JOIN products pr
            ON pr.id = p.product_id
        WHERE p.store_id = ?
        ORDER BY p.id DESC
        ''',
        (STORE_ID,)
    )

    if purchases.empty:
        st.info('No purchases recorded yet.')
    else:
        st.dataframe(purchases, use_container_width=True, hide_index=True)