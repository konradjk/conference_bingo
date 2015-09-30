__author__ = 'konrad'
import random
import datetime
import sys


def get_unfinished_card(db, email, conference):
    card = db.cards.find_one({'email': email, 'conference': conference, 'win': False}, fields={'_id': False})
    if card is None:
        return None
    else:
        return card['card']


def delete_unfinished_card(db, email, conference):
    db.cards.remove({
        'email': email,
        'conference': conference,
        'win': False
    })


def get_finished_cards(db, email, conference):
    cards = db.cards.find({'email': email, 'conference': conference, 'win': True})
    if cards is None:
        return None
    else:
        cards = list(cards)
        for card in cards:
            card['_id'] = str(card['_id'])
        return [x for x in sorted(cards, key=lambda k: k['index'])]


def create_new_card(db, conference):
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