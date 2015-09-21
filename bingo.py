
import pymongo
import random
import sys
import datetime
from flask import Flask, request, g, redirect, render_template
from bson.objectid import ObjectId

SELECTED_CUTOFF = 5

app = Flask(__name__)

app.config.update(dict(
    DB_HOST='localhost',
    DB_PORT=27017,
    DB_NAME='bingo',
    DEBUG=True,
    SECRET_KEY='development key',

    TERMS_FILE='bingo.txt'
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

    # Initialize database
    # Don't need to explicitly create tables with mongo, just indices

    db.terms.remove()
    db.terms.ensure_index('conference')

    # db.cards.remove()
    # db.cards.ensure_index('conference')
    # db.cards.ensure_index('email')

    # grab terms from list
    terms_list = open(app.config['TERMS_FILE'])
    for line in terms_list:
        term = line.strip()
        db.terms.insert({
            'conference': 'gi2014',
            'term': term
        })


def get_db():
    """
    Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'db_conn'):
        g.db_conn = connect_db()
    return g.db_conn


def get_bingo_terms(conference=None):
    db = get_db()
    if conference is None:
        return list(db.terms.find(fields={'_id': False}))
    else:
        return list(db.terms.find({'conference': conference}, fields={'_id': False}))


def create_new_card(conference):
    db = get_db()
    all_terms = [x['term'] for x in db.terms.find({'conference': conference}, fields={'_id': False})]
    random.shuffle(all_terms)
    raw_card = all_terms[:24]
    raw_card.insert(12, 'FREE SPACE')
    card_order = [raw_card[i*5:i*5+5] for i in range(5)]
    selected = dict([(x, False) for x in raw_card])
    selected['FREE SPACE'] = True
    card = {
        'order': card_order,
        'selected': selected
    }
    return card


def get_conferences():
    db = get_db()
    return list(set([x['conference'] for x in db.terms.find()]))


def get_unfinished_card(db, email, conference):
    card = db.cards.find_one({'email': email, 'conference': conference, 'win': False}, fields={'_id': False})
    if card is None:
        return None
    else:
        return card['card']


def get_finished_cards(db, email, conference):
    cards = db.cards.find({'email': email, 'conference': conference, 'win': True})
    if cards is None:
        return None
    else:
        cards = list(cards)
        for card in cards:
            card['_id'] = str(card['_id'])
        return [x for x in sorted(cards, key=lambda k: k['index'])]


def store_card(db, email, conference, card):
    all_cards = list(db.cards.find({'email': email, 'conference': conference}))
    index = 1 if len(all_cards) == 0 else max([x['index'] for x in all_cards]) + 1
    db.cards.insert({
        'conference': conference,
        'email': email,
        'card': card,
        'date_created': datetime.datetime.utcnow(),
        'date_modified': datetime.datetime.utcnow(),
        'win': False,
        'index': index,
        'name': ''
    })


def update_card_db(db, email, conference, new_card_selected, win):
    card = db.cards.find_one({
        'email': email,
        'conference': conference,
        'win': False
    })
    try:
        card['card']['selected'] = new_card_selected
        card['date_modified'] = datetime.datetime.utcnow()
        card['win'] = win
    except TypeError, e:
        print >> sys.stderr, e
        print >> sys.stderr, "Issue with card from %s @ %s" % (email, conference)
    if not card:
        print 'wat'
        sys.exit(1)
    db.cards.save(card)


def get_number_of_players(db, conference):
    return len(set([x['email'] for x in db.cards.find(
        {
            'conference': conference,
            'date_modified': {
                "$gt": datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
            }
        }
    )]))


@app.route('/')
def home():
    conferences = get_conferences()
    return render_template('homepage.html', conferences=conferences)


@app.route("/bingo", methods=["GET", "POST"])
def bingo():
    if request.method == 'POST':
        if len(request.form) == 0:
            request.form = request.get_json()
        if request.form is None:
            return redirect('/')
        db = get_db()
        conference = request.form['conference']
        email = request.form['email']
        if email == 'admin@admin':
            return redirect('/admin', code=307)
        card = get_unfinished_card(db, email, conference)
        number_playing = get_number_of_players(db, conference)
        finished_cards = get_finished_cards(db, email, conference)
        return render_template(
            "bingo.html",
            conference=conference,
            card=card,
            email=email,
            finished_cards=finished_cards,
            number_playing=number_playing
        )
    else:
        db = get_db()
        conference = request.args.get('conference')
        email = request.args.get('email')
        card = get_unfinished_card(db, email, conference)
        number_playing = get_number_of_players(db, conference)
        finished_cards = get_finished_cards(db, email, conference)
        return render_template(
            "bingo.html",
            conference=conference,
            card=card,
            email=email,
            finished_cards=finished_cards,
            number_playing=number_playing
        )


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
        card = create_new_card(request.form['conference'])
        store_card(db, request.form['email'], request.form['conference'], card)
        return redirect('/bingo', code=307)
    else:
        return redirect('/')


@app.route('/about')
def about():
    return render_template('about.html')


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
    card = db.cards.find_one({'win': True, '_id': ObjectId(request.args.get('id'))})
    card_returned = None
    if card is not None:
        card_returned = card['card']
        card_returned['date'] = card['date_modified']
        if card['name'] != '':
            card_returned['name'] = card['name']
    return render_template(
        'card.html',
        card=card_returned
    )


def delete_unfinished_card(db, email, conference):
    db.cards.remove({
        'email': email,
        'conference': conference,
        'win': False
    })


@app.route('/admin', methods=["POST"])
def admin():
    if request.form['password'] != 'gigigi':
        return redirect('/')
    db = get_db()
    conference = request.form['conference']
    terms = list(db.terms.find({'conference': conference}, fields={'_id': False}))
    cards = list(db.cards.find())
    terms_frequency = dict([(x['term'], 0) for x in terms])
    terms_selected = dict([(x['term'], 0) for x in terms])
    terms_frequency['FREE SPACE'] = len(cards)
    terms_selected['FREE SPACE'] = len(cards)
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