
from flask import Flask, request, render_template, url_for, flash, redirect, session
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, RadioField, ValidationError
from wtforms.validators import Required
import requests
import json

import os
import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, login_user, logout_user, current_user, UserMixin
from requests_oauthlib import OAuth2Session # If you haven't, need to pip install requests_oauthlib
from requests.exceptions import HTTPError
from flask_migrate import Migrate, MigrateCommand
from flask_script import Manager, Shell
from stuff import clientid, clientsecret

os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1' # So you can use http, not just https
basedir = os.path.abspath(os.path.dirname(__file__))


"""App Configuration"""
## See this tutorial for how to get your application credentials and set up what you need: http://bitwiser.in/2015/09/09/add-google-login-in-flask.html
#everything in the class below can be copied/pasted, except for client ID & secret
class Auth:
    """Google Project Credentials"""
    CLIENT_ID = clientid
    CLIENT_SECRET = clientsecret
    REDIRECT_URI = 'http://localhost:5000/gCallback' # Our (programmer's) decision
    # URIs determined by Google, below
    AUTH_URI = 'https://accounts.google.com/o/oauth2/auth'
    TOKEN_URI = 'https://accounts.google.com/o/oauth2/token'
    USER_INFO = 'https://www.googleapis.com/userinfo/v2/me'
    SCOPE = ['profile', 'email'] # Could edit for more available scopes -- if reasonable, and possible without $$


class Config:
    """Base config"""
    APP_NAME = "Test Google Login"
    SECRET_KEY = os.environ.get("SECRET_KEY") or "something secret"

#development environment, local to your machine
class DevConfig(Config):
    """Dev config"""
    DEBUG = True
    USE_RELOADER = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or "postgresql://localhost/recipeapp" # TODO: Need to create this database or edit URL for your computer
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True

#when you actually deploy it for users to use
class ProdConfig(Config):
    """Production config"""
    DEBUG = False
    USE_RELOADER = True
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or "postgresql://localhost/recipeapp" # If you were to run a different database in production, you would put that URI here. For now, have just given a different database name, which we aren't really using.
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_COMMIT_ON_TEARDOWN = True

# To set up different configurations for development of an application
config = {
    "dev": DevConfig,
    "prod": ProdConfig,
    "default": DevConfig
}

"""APP creation and configuration"""
app = Flask(__name__)
app.config.from_object(config['dev']) # Here's where we specify which configuration is being used for THIS Flask application instance, stored in variable app, as usual!
app.config['SECRET_KEY'] = 'hardtoguessstring'
app.config['HEROKU_ON'] = os.environ.get('HEROKU')
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('DATABASE_URL') or "postgresql://localhost/recipeapp"
app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False


db = SQLAlchemy(app)
manager = Manager(app)
#below commented out since we're not using migrations right now, can add later
# migrate = Migrate(app, db)
# manager.add_command('db', MigrateCommand)

#CAN JUST COPY/PASTE BELOW
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.session_protection = "strong" # New - because using sessions with oauth instead of our own auth verification


#MODELS

# Association table -

#TODO figure this out?? below, an example
#to_read = db.Table('to_read',db.Column('book_id',db.Integer, db.ForeignKey('books.id')),db.Column('user_id',db.Integer, db.ForeignKey('users.id'))) # Many to many, books to users
# Of course, access current user's books with query


class Recipe(db.Model):
    # don't need regular old constructor, can create Recipe objects using DB variables
    # def __init__(self, name, picURL, url):
    #     self.name = name
    #     self.picURL = picURL
    #     self.url = url
    __tablename__ = "recipes"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(200), unique=True,nullable=False)
    url = db.Column(db.String(400))
    picURL = db.Column(db.String(400))



class User(db.Model, UserMixin):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key = True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    avatar = db.Column(db.String(200))
    tokens = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow())
#TODO: modify below to establish relationship with recipes
    #books = db.relationship('Book',secondary=to_read,backref=db.backref('books',lazy='dynamic'),lazy='dynamic')


## IMPORTANT FUNCTION / MANAGEMENT
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

""" OAuth Session creation """
def get_google_auth(state=None, token=None):
    if token:
        return OAuth2Session(Auth.CLIENT_ID, token=token)
    if state:
        return OAuth2Session(
            Auth.CLIENT_ID,
            state=state,
            redirect_uri=Auth.REDIRECT_URI)
    oauth = OAuth2Session(
        Auth.CLIENT_ID,
        redirect_uri=Auth.REDIRECT_URI,
        scope=Auth.SCOPE)
    return oauth


#FORM CLASSES

class IngredForm(FlaskForm):
    ingredient = StringField('Search for a recipe: ', validators = [Required()])
    submit = SubmitField('Submit')

#TODO - delete these & replace with HTML forms? these are so small and pointless
class AddForm(FlaskForm):
    submit = SubmitField('Add to my recipe box')

class SeeRecipesForm(FlaskForm):
    submit = SubmitField('See my recipe box')

#HELPER FUNCTIONS
#TODO: THis section!

# def get_or_create_author(name, hometown):
#     pass # TODO: save and return new author object if one of the same name does not already exist; if so, return that one
#
# def get_or_create_book(book_title, author, hometown):
#     pass # TODO: if not a book by this title that already exists (let's go simple for now and identify books solely by their title), save author and associate its id with the new book instance, use current_user to append the created book to the current user, and return the book object, all committed to DB
#


#ROUTES AND VIEW FUNTIONS

#error handling routes
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500


#MAIN ROUTES

@app.route('/')
@login_required
def askForIngred():
    firstForm = IngredForm()

    return render_template('ingredIntake.html', form = firstForm)


@app.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('askForIngred'))
    google = get_google_auth()
    auth_url, state = google.authorization_url(
        Auth.AUTH_URI, access_type='offline')
    session['oauth_state'] = state
    return render_template('login.html', auth_url=auth_url)

@app.route('/gCallback')
def callback():
    if current_user is not None and current_user.is_authenticated:
        return redirect(url_for('askForIngred'))
    if 'error' in request.args: # Good Q: 'what are request.args here, why do they matter?'
        if request.args.get('error') == 'access_denied':
            return 'You denied access.'
        return 'Error encountered.'
    # print(request.args, "ARGS")
    if 'code' not in request.args and 'state' not in request.args:
        return redirect(url_for('login'))
    else:
        google = get_google_auth(state=session['oauth_state'])
        try:
            token = google.fetch_token(
                Auth.TOKEN_URI,
                client_secret=Auth.CLIENT_SECRET,
                authorization_response=request.url)
        except HTTPError:
            return 'HTTPError occurred.'
        google = get_google_auth(token=token)
        resp = google.get(Auth.USER_INFO)
        if resp.status_code == 200:
            # print("SUCCESS 200") # For debugging/understanding
            user_data = resp.json()
            email = user_data['email']
            user = User.query.filter_by(email=email).first()
            if user is None:
                # print("No user...")
                user = User()
                user.email = email
            user.name = user_data['name']
            # print(token)
            user.tokens = json.dumps(token)
            user.avatar = user_data['picture']
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('askForIngred'))
        return 'Could not fetch your information.'


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('askForIngred'))


recipe_objects = []
searchTerm = ""

@app.route('/recipes', methods = ['GET','POST'])
def getRecipes():
    form = IngredForm(request.form)
    print(form)

    print("FORM DATA",form.ingredient.data)

    if form.ingredient.data:
        global searchTerm
        searchTerm = form.ingredient.data

    if form.ingredient.data:
        recipe_objects.clear()
        edamam_result = requests.get('http://api.edamam.com/search', params={
        'q': form.ingredient.data,
        'app_id': 'fa50cd3a',
        'app_key': '45847a72028b77699b111aff32fab050'
        })

        print("RESPONSE",edamam_result.text)

        edamam_obj = json.loads(edamam_result.text)

        # print(edamam_obj, indent = 4)

        for recipe in edamam_obj["hits"]:
            tempRecipe = Recipe(
            name = recipe["recipe"]["label"],
            picURL = recipe["recipe"]["image"],
            url = recipe["recipe"]["url"])

            recipe_objects.append(tempRecipe)

    form1 = AddForm()
    recForm = SeeRecipesForm()

    return render_template('searchResults.html',
    recipes = recipe_objects,
    search = searchTerm,
    form = form1,
    form2 = recForm)


@app.route('/save/<recipeName>', methods = ['GET', 'POST'])
def saveRecipe(recipeName):
    if request.method == 'POST':
        name = recipeName

        #I have name, but to get other info I need (url, picurl), I'm looping
        #through the list of recipe objects to find a name match

        for recipe in recipe_objects:
            if recipe.name == name:
                url = recipe.url
                picURL = recipe.picURL


        recipe_obj = Recipe(name = name,
        url = url,
        picURL = picURL,
        user_id = current_user.id
        )
        db.session.add(recipe_obj)
        db.session.commit()

        flash("You added " + name + " to your recipe box!")

        return redirect(url_for('getRecipes'))

@app.route('/seeMyRecipes')
def getUsersRecipes():
    userRecipes = Recipe.query.filter_by(user_id = current_user.id).all()

    return render_template('myRecipes.html',
    recipes = userRecipes,
    name = current_user.name)

@app.route('/remove/<recipeName>')
def removeRecipe(recipeName):
    recipeToDelete = Recipe.query.filter_by(name = recipeName, user_id = current_user.id).first()
    #this ^ returns a Recipe object
    db.session.delete(recipeToDelete)
    db.session.commit()
    return redirect(url_for('getUsersRecipes'))


if __name__ == "__main__":
    db.create_all()
    manager.run()


# if __name__ == '__main__':
#     app.run(use_reloader=True,debug=True)
