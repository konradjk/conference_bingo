from flask.ext.script import Manager
from bingo import app
import bingo

manager = Manager(app)


@manager.command
def load_db():
    bingo.load_db()


if __name__ == "__main__":
    manager.run()

