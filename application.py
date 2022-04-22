import os
import datetime

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    s_n = db.execute("SELECT symbol,name,quantity FROM data WHERE id=?", session["user_id"])
    tmpr = db.execute("SELECT symbol FROM data WHERE id=?", session["user_id"])
    itotal = db.execute("SELECT total FROM data WHERE id=?", session["user_id"]) 

    symbol = []     # contains the symbols of the shares
    for t in tmpr:
        symbol.append(t['symbol'])

    new_price = []  # contains the updatated stock price

    # FUNCTION
    def price(sym):
        for s in sym:
            new_price.append(lookup(s)['price'])
    ################
    price(symbol)
    data = zip(s_n, new_price, itotal) 
    cash = db.execute("SELECT cash from users WHERE id=?", session["user_id"])[0]['cash']
    t1 = db.execute("SELECT SUM(total)  AS res FROM data WHERE id=?", session["user_id"])[0]['res']
    total = float(t1 or 0) + cash
    return render_template("index.html", data=data, cash=cash, total=total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        sym = request.form.get("symbol").upper()
        if not sym or (lookup(sym) is None):
            return apology("Invalid Symbol", 400)

        # Checks
        counts = request.form.get("shares")
        try:
            count = float(counts)
            if (count % 1 != 0) or (count < 0):
                return apology("Invalid share count", 400)
        except:
            return apology("Invalid share count", 400)

        count = int(count)
        av_bal = float(db.execute("SELECT cash FROM users where id=?", session["user_id"])[0]['cash'])
        stock_price = lookup(sym)['price']
        amount = stock_price * count
        if amount > av_bal:
            return apology("Insufficient funds", 403)

        new_bal = av_bal - amount
        sname = lookup(sym)['name']

        dtime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        p_sym = db.execute('SELECT symbol FROM data WHERE id=?', session["user_id"])
        prev_sym = []   # Contains the symbols of shares currently owned
        for ps in p_sym:
            prev_sym.append(ps['symbol'])

        if sym in prev_sym:
            quantity = db.execute("SELECT quantity FROM data WHERE id=? AND symbol=?", session["user_id"], sym)[0]['quantity']
            f_quantity = quantity + count
            amt = f_quantity * stock_price
            db.execute("UPDATE data SET quantity=?, total=? WHERE id=? AND symbol=?", f_quantity, amt, session["user_id"], sym)
        else:
            db.execute("INSERT INTO data (id, symbol, price, total, quantity, name) VALUES (?,?,?,?,?,?)",
                       session["user_id"], sym, stock_price, amount, count, sname)

        db.execute("INSERT INTO history(id, symbol, quantity, price, timestamp) VALUES (?,?,?,?,?)",
                   session["user_id"], sym, count, stock_price, dtime)
        db.execute("UPDATE users SET cash=? WHERE id=?", new_bal, session["user_id"])

        # Return to index
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM history WHERE id=?", session["user_id"])
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        data = lookup(request.form.get("symbol"))

        if data is None:
            return apology("Invalid Symbol", 400)

        return render_template("quoted.html", quote=data)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Check for the presence of values
    if request.method == "POST":

        if not request.form.get("username"):
            return apology("Please enter username", 400)
        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("Please enter and confirm the password", 400)

        names = db.execute("SELECT username FROM users")
        uname = [d['username'] for d in names]
        if request.form.get("username") in uname:
            return apology("Username already taken", 400)

        user = request.form.get("username")
        pwd = request.form.get("password")

        if pwd != request.form.get("confirmation"):
            return apology("Passwords do not match", 400)

        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", user,
                   generate_password_hash(pwd, method='pbkdf2:sha256', salt_length=8))
        return render_template("login.html")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":
        shares = db.execute("SELECT symbol FROM data WHERE id=?", session["user_id"])
        symbol = [d['symbol'] for d in shares]
        sym = request.form.get("symbol")    # symbol of the share to sell

        # check if received symbol is a valid symbol
        if sym not in symbol:
            return apology("You don't own this share", 400)
        # check for a valid share count
        digit = request.form.get('shares')
        if not digit.isdigit() or int(digit) < 1:
            return apology("Invalid shares count", 400)

        av_quantity = db.execute("SELECT quantity FROM data WHERE id=? AND symbol=?",
                                 session["user_id"], sym)[0]['quantity']
        count = int(digit)    # shares count to sell
        if count > av_quantity:
            return apology("You don't have enough shares", 400)

        d_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stock_price = lookup(sym)['price']
        rate = lookup(sym)['price']
        f_count = av_quantity - count
        f_total = f_count * rate

        # updating the quantity
        db.execute("UPDATE data SET quantity=? , total=? WHERE id=? AND symbol=?",
                   f_count, f_total, session["user_id"], sym)

        # adding to history
        db.execute("INSERT INTO history(id, symbol, quantity, price, timestamp) VALUES (?,?,?,?,?)",
                   session["user_id"], sym, -count, stock_price, d_time)

        # adding the cash
        av_cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]['cash']
        sold = rate * count
        db.execute("UPDATE users SET cash=? WHERE id=?", av_cash + sold, session["user_id"])

        # removing zero quantity(share count) entries
        db.execute("DELETE FROM data WHERE quantity=0")

        return redirect("/")

    else:
        symbol = db.execute("SELECT DISTINCT symbol FROM data where id=?", session["user_id"])
        return render_template("sell.html", symbol=symbol)


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
