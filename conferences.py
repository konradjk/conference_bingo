__author__ = 'konrad'
import datetime


def get_bingo_terms(db, conference=None):
    if conference is None:
        return list(db.terms.find(fields={'_id': False}))
    else:
        return list(db.terms.find({'conference': conference}, fields={'_id': False}))


def get_conferences(db):
    return list(set([x['conference'] for x in db.terms.find()]))


def get_number_of_players(db, conference):
    return len(set([x['email'] for x in db.cards.find(
        {
            'conference': conference,
            'date_modified': {
                "$gt": datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
            }
        }
    )]))