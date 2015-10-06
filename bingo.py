
import pymongo
from flask import *
from bson.objectid import ObjectId
import bson.errors
import glob
import os
from cards import *
from conferences import *

SELECTED_CUTOFF = 5

app = Flask(__name__)

app.config.update(dict(
    DB_HOST='localhost',
    DB_PORT=27017,
    DB_NAME='bingo',
    DEBUG=True,
    SECRET_KEY='development key',

    TERMS_FILES=glob.glob('terms/*.txt')
))


def connect_db():
    """
    Connects to the specific database.
    """
    client = pymongo.MongoClient(host=app.config['DB_HOST'], port=app.config['DB_PORT'])
    return client[app.config['DB_NAME']]


def load_db():
    """
    Load the database
    """
    db = get_db()

    db.terms.remove()
    db.terms.ensure_index('conference')

    delete_cards()

    # grab terms from all lists
    for terms_file in app.config['TERMS_FILES']:
        load_conference_from_file(terms_file)


def load_conference_from_file(terms_file):
    db = get_db()
    conference = os.path.basename(terms_file).split('.txt')[0]
    db.terms.remove({'conference': conference})
    terms_list = open(terms_file)
    for line in terms_list:
        term = line.strip().replace('.', '\u002E').replace('$', '\u0024')
        db.terms.insert({
            'conference': conference,
            'term': term,
            'date_created': datetime.datetime.utcnow()
        })


def delete_cards():
    db = get_db()
    db.cards.remove()
    db.cards.ensure_index('conference')
    db.cards.ensure_index('email')


def get_db():
    """
    Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'db_conn'):
        g.db_conn = connect_db()
    return g.db_conn


@app.route('/')
def home():
    username = request.cookies.get('username')
    conference = request.cookies.get('conference')
    if username is not None:
        return return_bingo_card(username, conference)
    else:
        return basic_homepage()


def basic_homepage():
    db = get_db()
    conferences = get_conferences(db)
    return render_template('homepage.html', conferences=conferences)


@app.route("/bingo", methods=["GET", "POST"])
def bingo():
    if request.method == 'POST':
        if len(request.form) == 0:
            request.form = request.get_json()
        if request.form is None:
            return redirect('/')
        conference = request.form['conference']
        email = request.form['email']
        if email == 'admin@admin':
            return redirect('/admin', code=307)
        return return_bingo_card(email, conference)
    else:
        conference = request.args.get('conference')
        email = request.args.get('email')
        return return_bingo_card(email, conference)


def return_bingo_card(email, conference):
    db = get_db()
    card = get_unfinished_card(db, email, conference)
    number_playing = get_number_of_players(db, conference)
    finished_cards = get_finished_cards(db, email, conference)
    resp = make_response(render_template(
        "bingo.html",
        conference=conference,
        card=card,
        email=email,
        finished_cards=finished_cards,
        number_playing=number_playing
    ))
    resp.set_cookie('username', email)
    resp.set_cookie('conference', conference)
    return resp


@app.route("/update_card", methods=["GET", "POST"])
def update_card():
    db = get_db()
    if request.method == 'POST':
        update_card_db(db, request.json['email'], request.json['conference'], request.json['card'], False)
        return str(get_number_of_players(db, request.json['conference']))
    else:
        return redirect('/')


@app.route("/update_card_win", methods=["GET", "POST"])
def update_card_win():
    db = get_db()
    if request.method == 'POST':
        card = db.cards.find_one({
            'email': request.form['email'],
            'conference': request.form['conference'],
            'win': False
        })
        card['win'] = True
        card['name'] = request.form['bingo-card-name']
        db.cards.save(card)
        return redirect('/bingo', code=307)
    else:
        return redirect('/')


@app.route("/create_card", methods=["GET", "POST"])
def create_card():
    db = get_db()
    if request.method == 'POST':
        card = create_new_card(db, request.form['conference'])
        store_card(db, request.form['email'], request.form['conference'], card)
        resp = make_response(redirect('/bingo', code=307))
        resp.set_cookie('username', request.form['email'])
        resp.set_cookie('conference', request.form['conference'])
        return resp
    else:
        return redirect('/')


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/logout')
def logout():
    resp = make_response(basic_homepage())
    resp.set_cookie('username', '', expires=0)
    resp.set_cookie('conference', '', expires=0)
    return resp


@app.route('/undo_card', methods=["GET", "POST"])
def undo_card():
    if request.method == 'POST':
        db = get_db()
        delete_unfinished_card(db, request.form['email'], request.form['conference'])
        card = db.cards.find_one({
            'email': request.form['email'],
            'conference': request.form['conference'],
            'index': int(request.form['bingo-undo-number'])
        })
        card['win'] = False
        db.cards.save(card)
        return redirect('/bingo', code=307)
    else:
        return redirect('/')


@app.route('/permalink')
def permalink():
    db = get_db()
    card_returned = None
    try:
        card = db.cards.find_one({'win': True, '_id': ObjectId(request.args.get('id'))})
        if card is not None:
            card_returned = card['card']
            card_returned['date'] = card['date_modified']
            if card['name'] != '':
                card_returned['name'] = card['name']
    except bson.errors.InvalidId:
        pass
    return render_template(
        'card.html',
        card=card_returned
    )


@app.route('/admin', methods=["POST"])
def admin():
    if request.form['password'] != 'gigigi':
        return redirect('/')
    db = get_db()
    conference = request.form['conference']
    terms = list(db.terms.find({'conference': conference}, fields={'_id': False}))
    cards = list(db.cards.find({'conference': conference}))
    terms_frequency = dict([(x['term'], 0) for x in terms])
    terms_selected = dict([(x['term'], 0) for x in terms])
    terms_frequency['FREE SPACE'] = 0
    terms_selected['FREE SPACE'] = 0
    card_info = {}
    for card in cards:
        id = str(card['_id'])
        card_info[id] = card
        card_info[id]['_id'] = str(card_info[id]['_id'])
        card_info[id]['selected'] = 0
        for term in card['card']['selected']:
            if term not in terms_frequency:
                terms_frequency[term] = 0
                terms_selected[term] = 0
            terms_frequency[term] += 1
            if card['card']['selected'][term]:
                terms_selected[term] += 1
                card_info[id]['selected'] += 1
    sorted_terms = sorted(terms_selected.items(), key=lambda x: x[1], reverse=True)
    sorted_cards = sorted(card_info.items(), key=lambda x: x[1]['selected'], reverse=True)
    for id in card_info:
        card = card_info[id]
        card_info[id]['selected_concordant'] = 0
        for term in card['card']['selected']:
            if card['card']['selected'][term] and terms_selected[term] >= SELECTED_CUTOFF:
                card_info[id]['selected_concordant'] += 1
    return render_template(
        'admin.html',
        conference=conference,
        terms_seen=terms_frequency,
        cards=sorted_cards,
        terms_selected=sorted_terms,
        number_playing=get_number_of_players(db, conference)
    )


if __name__ == '__main__':
    app.run(port=5001)