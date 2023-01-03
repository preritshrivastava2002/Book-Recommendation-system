from msilib.schema import tables
from venv import create
from flask import Flask, jsonify, make_response, render_template, request, redirect, session, url_for, flash, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import pickle
import numpy as np
from markupsafe import escape
from sqlalchemy import false
from werkzeug.security import check_password_hash, generate_password_hash
from uuid import uuid1
import xmltodict
import urllib.request as urllib2
from urllib.parse import quote
import json
import os
from flask_ngrok import run_with_ngrok
import webbrowser
from dotenv import load_dotenv


popular_df = pickle.load(open('popular.pkl','rb'))
pt = pickle.load(open('pt.pkl','rb'))
books = pickle.load(open('books.pkl','rb'))
similarity_scores = pickle.load(open('similarity_scores.pkl','rb'))


load_dotenv()
app = Flask(__name__)
# run_with_ngrok(app)

CORS(app)
ENV = 'dev'

LOCAL_DB_URL = "postgresql://postgres:prerit@localHost:5432/Books"
REMOTE_DB_URL = os.getenv("REMOTE_DB_URL")
SECRET_KEY = "prerit"

# Setting database configs
if ENV == 'dev':
    app.debug = True
    app.config['SQLALCHEMY_DATABASE_URI'] = LOCAL_DB_URL
else:
    app.debug = False
    app.config['SQLALCHEMY_DATABASE_URI'] = REMOTE_DB_URL

app.config['SQL_ALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['SECRET_KEY'] = SECRET_KEY

db = SQLAlchemy(app)


# custom functions
def customid():
    idquery = db.session.query(Ratings).order_by(Ratings.col_id.desc()).first()
    last_id = int(idquery.col_id)
    next_id = int(last_id) + 1
    return next_id


def user_id(userid):
    if db.session.query(Ratings).filter(Ratings.username == userid).count() == 0:
        idquery = db.session.query(Ratings).order_by(Ratings.user_id.desc()).first()
        last_id = int(idquery.user_id)
        next_id = int(last_id) + 1
        print(next_id)
        return next_id
    else:
        idquery = db.session.query(Ratings).filter(Ratings.username == userid).first()
        idquery_old = idquery.user_id
        return idquery_old


# def idcounter():
#     iding = db.session.query(GrBook)
#     iding.order_by(GrBook.gr_id.desc()).first()
#     last_id = int(iding.gr_id)
#     next_id = int(last_id) + 1
#     return next_id


def parse_xml(request_xml):
    content_dict = xmltodict.parse(request_xml)
    return jsonify(content_dict)


# Building user model
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(200))
    password = db.Column(db.String(200))
    password_hash = db.Column(db.String(200))

    def __init__(self, cnt, username, password, password_hash):
        self.id = cnt
        self.username = username
        self.password = password
        self.password_hash = password_hash


# Building ratings model
class Ratings(db.Model):
    __tablename__ = 'ratings'
    col_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    rating = db.Column(db.Integer)
    book_id = db.Column(db.Integer)
    username = db.Column(db.String(200))
    isbn10 = db.Column(db.String(200))

    def __init__(self, col_id, user_id, rating, book_id, username, isbn10):
        self.col_id = col_id
        self.user_id = user_id
        self.rating = rating
        self.book_id = book_id
        self.username = username
        self.isbn10 = isbn10


# Building the new recommendations model
class NewRecs(db.Model):
    __tablename__ = 'new_recs'
    user_id = db.Column(db.Integer)
    book_id = db.Column(db.Integer)
    prediction = db.Column(db.Float,primary_key=True)

    def __init__(self, user_id, book_id, prediction):
        self.user_id = user_id
        self.book_id = book_id
        self.prediction = prediction


# Building the lookup between book_id and gr_book_id
class GrBook(db.Model):
    __tablename__ = 'gr_books'
    gr_id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer)

    def __init__(self, gr_id, book_id):
        self.gr_id = gr_id
        self.book_id = book_id


################################
# Building routes for the site #
################################

# Home page
@app.route('/')
def index():
    return render_template("base.html")


# registration page
cnt=15
@app.route('/register', methods=["GET", "POST"])
def register():
    # print(1)
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        password_hash = generate_password_hash(password)
        # print("a")
        if username == '' or password == '':
            return render_template('register.html', message='Please include a name and/or password.')
        # print("c")

        if db.session.query(User).filter(User.username == username).count() == 0:
            # print("d")
            global cnt
            cnt += 1
            user = User(cnt,username, password, password_hash)
            db.session.add(user)
            db.session.commit()
            session['username'] = user.username
            session['user_id'] = user_id(session.get('username'))
            return redirect(url_for('get_profile'))
        else:
            return render_template('register.html', message='Sorry, this username is already taken.')
        # print("f")

        return render_template('register.html')

    else:
        # print("g")
        return render_template('register.html')


# sign-in page
@app.route('/sign-in', methods=["GET", "POST"])
def sign_in():
    if request.method == 'POST':
        username_entered = request.form['username']
        password_entered = request.form['password']
        user = db.session.query(User).filter(User.username == username_entered).first()
        if user is not None and check_password_hash(user.password_hash, password_entered):
            session['username'] = user.username
            session['user_id'] = user_id(session.get('username'))
            return redirect(url_for('get_profile'))
        return render_template('signin.html',
                               message="Sorry, either your username does not exist or your password does not match.")
    else:
        return render_template('signin.html')


# sign-out page
@app.route('/sign-out', methods=["GET", "POST"])
def sign_out():
    if request.method == 'POST':
        session.pop('username', None)
        return redirect(url_for('sign_in'))
    else:
        return render_template('signout.html')


# loads the user profile
@app.route('/profile', methods=['GET', 'POST'])
def get_profile():
    if request.method == 'GET':
        userid = user_id(session.get('username'))
        username = session.get('username')
        ratings = db.session.query(Ratings).filter(Ratings.user_id == userid).all()

        ratings_list = []
        for i in ratings:
            gr_bookid = db.session.query(GrBook).filter(GrBook.gr_id == i.book_id).first().book_id
            ratings_list.append([gr_bookid, i.rating])

        bk = []
        for i in ratings_list:
            response_string = 'https://www.goodreads.com/book/show?id=' + str(i[0]) + '&key=Ev590L5ibeayXEVKycXbAw'
            xml = urllib2.urlopen(response_string)
            data = xml.read()
            xml.close()
            data = xmltodict.parse(data)
            gr_data = json.dumps(data)
            goodreads_fnl = json.loads(gr_data)
            gr = goodreads_fnl['GoodreadsResponse']['book']
            bk.append(dict(id=gr['id'], book_title=gr['title'], image_url=gr['image_url'], rating=i[1]))

        book = dict(work=bk)
        return render_template('profile.html', recs=book, username=username)
    else:
        return 'Error in login process...'


# search books page
@app.route("/search", methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        response_string = 'https://www.goodreads.com/search/index.xml?format=xml&key=Ev590L5ibeayXEVKycXbAw&q=' + quote(
            request.form.get("title"))
        xml = urllib2.urlopen(response_string)
        data = xml.read()
        xml.close()
        data = xmltodict.parse(data)
        gr_data = json.dumps(data)
        goodreads_fnl = json.loads(gr_data)
        gr = goodreads_fnl['GoodreadsResponse']['search']['results']

        if not request.form.get("title"):
            return ("Please enter a book title below.")

        return render_template("searchResults.html", books=gr)

    else:
        username = session.get('username')
        return render_template("search.html", username=username)


# book details route
@app.route("/bookDetails/<book_id>")
def bookDetails(book_id):
    response_string = 'https://www.goodreads.com/book/show?id=' + book_id + '&key=Ev590L5ibeayXEVKycXbAw'
    xml = urllib2.urlopen(response_string)
    data = xml.read()
    xml.close()
    data = xmltodict.parse(data)
    gr_data = json.dumps(data)
    goodreads_fnl = json.loads(gr_data)
    gr = goodreads_fnl['GoodreadsResponse']['book']
    return render_template("bookDetails.html", book=gr)


# submitting new book ratings
@app.route("/new-rating", methods=['POST'])
def postnew():
    if request.method == 'POST':
        col_id = customid()
        userid = user_id(session.get('username'))
        rating = request.form['rating']
        book_id = request.form.get('bookid')
        username = session.get('username')
        isbn10 = request.form.get('isbn10')

        if db.session.query(GrBook).filter(GrBook.book_id == book_id).count() == 0:
            # gr_id = idcounter()
            gr_id = book_id
            grdata = GrBook(gr_id, book_id)
            db.session.add(grdata)
            db.session.commit()
        else:
            grfilter = db.session.query(GrBook).filter(GrBook.book_id == book_id).first()
            gr_id = grfilter.gr_id

        data = Ratings(col_id, userid, rating, gr_id, username, isbn10)
        db.session.add(data)
        db.session.commit()
        return render_template('success.html')


# getting book recommendations
@app.route("/recs", methods=['GET'])
def getrecs():
    if request.method == 'GET':
        userid = user_id(session.get('username'))
        recs = db.session.query(NewRecs).filter(NewRecs.user_id == userid).all()
        # print(userid)
        recs_list = []
        for i in recs:
            gr_bookid = db.session.query(Ratings).filter(Ratings.book_id == i.book_id).first().book_id
            recs_list.append(gr_bookid)
            # print(type(recs))
            # print(GrBook.book_id)
            # print(i.book_id)
        bk = []
        for i in recs_list:
            response_string = 'https://www.goodreads.com/book/show?id=' + str(i) + '&key=Ev590L5ibeayXEVKycXbAw'
            xml = urllib2.urlopen(response_string)
            data = xml.read()
            xml.close()
            data = xmltodict.parse(data)
            gr_data = json.dumps(data)
            goodreads_fnl = json.loads(gr_data)
            gr = goodreads_fnl['GoodreadsResponse']['book']
            bk.append(dict(id=gr['id'], book_title=gr['title'], image_url=gr['image_url']))

        book = dict(work=bk)
        return render_template('recs.html', recs=book)
    else:
        return "No Data"


#form other data
@app.route('/book')
def book():
    return render_template('index.html',
                           book_name = list(popular_df['Book-Title'].values),
                           author=list(popular_df['Book-Author'].values),
                           image=list(popular_df['Image-URL-M'].values),
                           votes=list(popular_df['num_ratings'].values),
                           rating=list(popular_df['avg_rating'].values)
                           )

@app.route('/recommend')
def recommend_ui():
    return render_template('recommend.html')

@app.route('/recommend_books',methods=['post'])
def recommend():
    user_input = request.form.get('user_input')
    index = np.where(pt.index == user_input)[0][0]
    similar_items = sorted(list(enumerate(similarity_scores[index])), key=lambda x: x[1], reverse=True)[1:5]

    data = []
    for i in similar_items:
        item = []
        temp_df = books[books['Book-Title'] == pt.index[i[0]]]
        item.extend(list(temp_df.drop_duplicates('Book-Title')['Book-Title'].values))
        item.extend(list(temp_df.drop_duplicates('Book-Title')['Book-Author'].values))
        item.extend(list(temp_df.drop_duplicates('Book-Title')['Image-URL-M'].values))

        data.append(item)

    print(data)

    return render_template('recommend.html',data=data)


if __name__ == '__main__':
    # webbrowser.open_new('http://127.0.0.1:5000/')
    app.run(debug=True)