from flask import Flask, request, render_template, redirect, url_for
import sqlite3, datetime, hashlib, time, sched
#from flask_socketio import SocketIO

app = Flask(__name__)

#app.config['SECRET_KEY']='iusdhfaukjxnmxcvnzksfdakhfowehroh'
#socketio = SocketIO(app)
#
#データベース接続用
def connect_db(db_name):
    return sqlite3.connect(db_name)

# hash
def get_hash(word, salt):
    #salt = os.urandom(16) #saltは最低16バイト
    iter = 100000 #反復回数は100000回以上
    return hashlib.pbkdf2_hmac('sha256', word.encode('utf-8'), salt.encode('utf-8'), iter)

# ユーザdb
with connect_db('user.db') as conn:
    cur = conn.cursor()

    # アカウントテーブル
    # user_id : ユーザID(主キー)、username : ユーザネーム、password : パスワー>ド
    sql = '''
    CREATE TABLE IF NOT EXISTS account
    (user_id INTEGER PRIMARY KEY,
    username TEXT UNIQUE,
    password TEXT)
    '''
    cur.execute(sql)
    
    # 訪問者テーブル
    sql = '''
    CREATE TABLE IF NOT EXISTS visitor
    (id INTEGER PRIMARY KEY,
    time TEXT)
    '''

    cur.execute(sql)
    
# conn.close()

with connect_db('room.db') as conn:
    cur = conn.cursor()
    # ルームテーブル
    # room_id : ルームID, passward : パスワード
    sql = '''
    CREATE TABLE IF NOT EXISTS room
    (room_id INTEGER PRIMARY KEY,
    room_name TEXT,
    password TEXT)
    '''
    cur.execute(sql)

    sql = '''
    CREATE TABLE IF NOT EXISTS roommembers
    (room_id INTEGER,
    room_member TEXT)
    '''
    cur.execute(sql)
# conn.close()

@app.route('/')
def hello():
    time = datetime.datetime.now()
    with connect_db('user.db') as conn:
        cur = conn.cursor()
        sql = '''
        insert into visitor(time)
        VALUES(?)
        '''
        cur.execute(sql,[time])
        sql = '''
        SELECT id FROM visitor
        WHERE time = ?
        '''
        cur.execute(sql,[time])
        visitor_number = cur.fetchone()
    # conn.close()

    return render_template('index.html',visitor_number=visitor_number[0])

#
# login用
#

@app.route('/login/')
def show_login_form(notice=None):
    return render_template('login.html', notice=notice if notice else '')

@app.route('/login/', methods=['POST'])
def login():
    # ユーザdbに接続して認証
    with connect_db('user.db') as conn:
        cur = conn.cursor()

        user_id = request.form["user_id"]
        password = request.form["password"]
        
        hash_pass = get_hash(password, str(user_id)) #ハッシュ化

        sql = """
        select username from account
        where user_id=? and password=?
        """
        cur.execute(sql, [user_id, hash_pass])
        exist = cur.fetchone()
    # conn.close()

    if exist:
        username = exist[0] #tuple -> str
        return redirect(url_for('show_user_page', username=username))
    else:
        return show_login_form(notice='ユーザIDまたはパスワードが間違っています。')


@app.route('/account/')
def show_account_form(notice=None):
    return render_template('newaccount.html', notice=notice if notice else '')

@app.route('/account/', methods=['POST'])
def create_account():
    # ユーザdbに接続して新規アカウント作成
    with connect_db('user.db') as conn:
        cur = conn.cursor()

        user_id = request.form["user_id"]
        username = request.form["username"]
        password = request.form["password"]

        hash_pass = get_hash(password, str(user_id)) #ハッシュ化
        
        sql = """
        select username from account
        where user_id=?
        """
        cur.execute(sql, [user_id])
        exist = cur.fetchone()

        if exist:
            #conn.close()
            return show_account_form(notice='ユーザIDが既に存在します。')
        
        sql = """
        select user_id from account
        where username=?
        """
        cur.execute(sql, [username])
        exist = cur.fetchone()
        
        if exist:
            #conn.close()
            return show_account_form(notice='ユーザ名が既に存在します。')
        
        sql = """
        insert into account
        VALUES(?, ?, ?)
        """
        
        cur.execute(sql,[user_id, username, hash_pass])
    # conn.close()

    return show_login_form()

#
# chat用
#

@app.route('/<username>/user_page/', methods=["GET"])
def return_user_page(username):
    room_id = request.args.get("room_id")
    #out_room(username=username, room_id=room_id)
    with connect_db('room.db') as conn:
        cur = conn.cursor()
        sql = """
        DELETE from roommembers
        where room_id=? and room_member=?
        """
        cur.execute(sql, [room_id, username])
    return render_template('user_page.html', username=username)

def exist_member(room_id, room_member):
    with connect_db('room.db') as conn:
        # 1時間以内にメッセージを送っていないユーザは"現在のユーザ"から削除
        cur = conn.cursor()
        # 副問い合わせ(サブクエリ)でアクティブでないメンバーを削除
        sql = """
        SELECT room_member FROM roommembers
        WHERE room_id=? and room_member=?
        """
        cur.execute(sql, [room_id, room_member])
        exist = cur.fetchall()
        if exist:
            return True
        else:
            return False
    
"""
一時間メッセージを送らずにいるといないことになってしまう
"""
def update_members(room_id, room_member):
    with connect_db('room.db') as conn:
        # 1時間以内にメッセージを送っていないユーザは"現在のユーザ"から削除
        cur = conn.cursor()
        # 副問い合わせ(サブクエリ)でアクティブでないメンバーを削除
        sql = """
        DELETE FROM roommembers
        WHERE NOT EXISTS (SELECT DISTINCT room_member FROM %s
                          WHERE time BETWEEN ? AND ?)
        """
        
        table_name = '_' + str(room_id)
        sql = sql % table_name
        
        current = str(datetime.datetime.now()) # 現在時間
        last = current[:12] + str( int(current[12]) - 1) + current[13:] # 1時間前
        
        cur.execute(sql, [last, current])

def add_members(room_id, room_member):
    with connect_db('room.db') as conn:
        cur = conn.cursor()
        sql = """
        INSERT INTO roommembers
        VALUES(?,?)
        """
        cur.execute(sql, [room_id, room_member])

@app.route('/<username>/user_page/', methods=["POST"])
def show_user_page(username, notice=None):
    return render_template('user_page.html', username=username, notice=notice if notice else '')

@app.route('/<username>/room/', methods=["POST"])
def login_room(username):
    # ルームdbに接続して認証
    with connect_db('room.db') as conn:
        cur = conn.cursor()
        room_id = request.form["room_id"]
        password = request.form["password"]
        hash_pass = get_hash(password, str(room_id))
        sql = """
        select room_name from room
        where room_id=? and password=?
        """
        cur.execute(sql, [room_id, hash_pass])
        exist = cur.fetchone()
    # conn.close()
    if exist: #and (not exist_member(room_id=room_id, room_member=username)):
        room_name = exist[0]
        update_members(room_id=room_id, room_member=username)
        add_members(room_id=room_id, room_member=username)
        in_room(username=username, room_id=room_id)
        return redirect(url_for('load_chat', username=username, room_name=room_name, room_id=room_id))
        #return start_chat(username=username, room_name=exist[0], room_id=room_id)
    else:
        return show_user_page(username=username, notice='ルームIDまたはパスワードが間違っています。')

@app.route('/<username>/newroom/')
def show_newroom_form(username, notice=None):
    return render_template('newroom_form.html', username=username, notice=notice if notice else '')

@app.route('/<username>/newroom/', methods=['POST'])
def create_room(username):
    # ルームdbに接続し新規ルームの作成
    with connect_db('room.db') as conn:
        cur = conn.cursor()

        room_id = request.form["room_id"]
        password = request.form["password"]

        hash_pass = get_hash(password, str(room_id)) #ハッシュ化
        
        sql = """
        select room_name from room
        where room_id=?
        """
        cur.execute(sql, [room_id])
        exist = cur.fetchone()

        if exist:
            return show_newroom_form(username=username, notice='ルームIDが既に存在します。')

        room_name = request.form["room_name"]
        sql = """
        insert into room
        VALUES(?, ?, ?)
        """
        cur.execute(sql,[room_id, room_name, hash_pass])

    with connect_db('room.db') as conn:
        cur = conn.cursor()
        # ルームテーブル
        # room_id : ルームID, passward : パスワード
        sql = '''
        CREATE TABLE IF NOT EXISTS %s
        (room_member TEXT,
        message TEXT,
        time TEXT)
        '''
        table_name = '_' + str(room_id)
        sql = sql % table_name
        cur.execute(sql)
    
    return show_user_page(username=username)

def load_messages(room_id, last=None, current=None):
    if last:
        with sqlite3.connect('room.db') as conn:
            cur = conn.cursor()
            # ルームテーブル
            # room_id : ルームID, passward : パスワード
            sql = '''
            SELECT * FROM %s
            WHERE time BETWEEN ? AND ? 
            ORDER BY time DESC
            '''
            table_name = '_' + str(room_id)
            sql = sql % table_name
            cur.execute(sql, [last, current])
            messages = cur.fetchall()
        # conn.close()
    else:
        with sqlite3.connect('room.db') as conn:
            cur = conn.cursor()
            # ルームテーブル
            # room_id : ルームID, passward : パスワード
            sql = '''
            SELECT * FROM %s
            ORDER BY time DESC
            '''
            table_name = '_' + str(room_id)
            sql = sql % table_name
            cur.execute(sql)
            messages = cur.fetchall()

    return messages 
'''
def reloader(username, room_id, room_name):
    time.sleep(1)
    messages = load_messages(room_id)
    return redirect(url_for('reload', username=username, room_id=room_id, room_name=room_name, messages=messages))
'''

def get_members(room_id):
    with connect_db('room.db') as conn:
        cur = conn.cursor()
        sql = """
        select room_member from roommembers
        where room_id=?
        """
        cur.execute(sql, [room_id])
        room_members = cur.fetchall()
    return room_members
    
def in_room(username, room_id):
    with sqlite3.connect('room.db') as conn:
        cur = conn.cursor()
        message = f"{username}さんが入室しました。"
        sql = '''
        INSERT INTO %s
        VALUES(?,?,?)
        '''
        table_name = '_' + str(room_id)
        sql = sql % table_name
        cur.execute(sql, ["server", message, datetime.datetime.now()])

def out_room(username, room_id):
    with sqlite3.connect('room.db') as conn:
        cur = conn.cursor()
        message = f"{username}さんが退出しました。"
        sql = '''
        INSERT INTO %s
        VALUES(?,?,?)
        '''
        table_name = '_' + str(room_id)
        sql = sql % table_name
        cur.execute(sql, ["server", message, datetime.datetime.now()])
        

@app.route('/<username>/room/<room_name>/reload/')
def reload(username, room_name):
    room_id = request.args.get('room_id')
    messages = load_messages(room_id)
    room_members = get_members(room_id)
    return render_template('room.html', username=username, room_id=room_id, room_name=room_name, messages=messages, room_members=room_members)

@app.route('/<username>/room/<room_name>/')
def load_chat(username, room_name):
    room_id = request.args.get('room_id')
    messages = load_messages(room_id)
    room_members = get_members(room_id)
    return render_template('room.html', username=username, room_id=room_id, room_name=room_name, messages=messages, room_members=room_members)

@app.route('/<username>/room/<room_name>/', methods=['POST'])
def send_message(username, room_name):
    room_id = request.form["room_id"]
    message = request.form["message"]
    if message: # if message exists
        with sqlite3.connect('room.db') as conn:
            cur = conn.cursor()
            sql = '''
            INSERT INTO %s
            VALUES(?,?,?)
            '''
            table_name = '_' + str(room_id)
            sql = sql % table_name
            cur.execute(sql, [username, message, datetime.datetime.now()])
    
    messages = load_messages(room_id)
    update_members(room_id=room_id, room_member=username)
    room_members = get_members(room_id)
    return render_template('room.html', username=username, room_id=room_id, room_name=room_name, messages=messages, room_members=room_members)

if __name__ == '__main__':
    app.run(port=12345, debug=True) # ポートを指定。サーバを立ち上げた時にデバッグ出力を表示