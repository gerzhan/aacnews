import os
import os.path as op
import datetime
import mailchimp
from dateutil.relativedelta import relativedelta
from flask import Flask, request, render_template, redirect, request, url_for
from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.admin import BaseView, expose, helpers

from wtforms import validators

from flask.ext import admin, login
from flask.ext.admin.contrib import sqla
from flask.ext.admin.contrib.sqla import filters
from flask.ext.admin.actions import action

from sqlalchemy import func, and_
from flask.ext.wtf import Form
from wtforms import StringField, PasswordField, BooleanField, SubmitField, form, fields
from wtforms.validators import Required, Email, Length

from collections import defaultdict
from jinja2 import Template


# Create application
app = Flask(__name__)

# Create dummy secrey key so we can use sessions
app.config['SECRET_KEY'] = '123456790'

# Create in-memory database
app.config['DATABASE_FILE'] = 'aacnews_db.sqlite'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + app.config['DATABASE_FILE']
app.config['SQLALCHEMY_ECHO'] = True
app.config['MAILCHIMP_CAMPAIGN_NAME'] = 'Dear friends'
db = SQLAlchemy(app)


login_manager = login.LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return db.session.query(User).get(user_id)

#Other
def dump_datetime(value):
    """Deserialize datetime object into string form for JSON processing."""
    if value is None:
        return None
    return value.strftime("%Y-%m-%d")

def get_mailchimp_api():
    return mailchimp.Mailchimp('03af8993cd1ecfb5db51d7f4e38eef26-us9') 

# Create models
class Type(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.Unicode(64), unique=True)

    def __unicode__(self):
        return self.name

class Newsletter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.Unicode(128), unique=True)
    date = db.Column(db.DateTime)
    preamble = db.Column(db.Text, nullable=False)
    spoiler = db.Column(db.Unicode(255), unique=True)
    html = db.Column(db.LargeBinary)
    
    def __unicode__(self):
        return self.title


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120))
    text = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime)
    url = db.Column(db.Text, nullable=True)
    publish = db.Column(db.Boolean)

    author = db.Column(db.String(120))
        
    type_id = db.Column(db.Integer(), db.ForeignKey(Type.id))
    type = db.relationship('Type', backref='types')

    def __unicode__(self):
        return self.title

    @property
    def serialize(self):
       return {
           'title': self.title,
           'date': dump_datetime(self.date),
           'author': self.author,
           'text': self.text,
           'url': self.url
       }

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login =  db.Column(db.String(120), unique=True)
    password = db.Column(db.String(64))

    # Flask-Login integration
    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

    # Required for administrative interface
    def __unicode__(self):
        return self.login

# Define login and registration forms (for flask-login)
class LoginForm(form.Form):
    login = fields.TextField(validators=[validators.required()])
    password = fields.PasswordField(validators=[validators.required()])

    def validate_login(self, field):
        user = self.get_user()

        if user is None:
            raise validators.ValidationError('Invalid user')

        if user.password != self.password.data:
            raise validators.ValidationError('Invalid password', self.password)


    def get_user(self):
        return db.session.query(User).filter_by(login=self.login.data).first()


# Flask views
@app.route('/')
def index():
    return '<a href="/admin/">Click me to get to Admin!</a>'


# Customized Post model admin
class PostAdmin(sqla.ModelView):
    # Visible columns in the list view
    column_exclude_list = ['text']

    # List of columns that can be sorted. For 'user' column, use User.username as
    # a column.
    column_sortable_list = ('title', 'author', 'publish', 'date')

    # Rename 'title' columns to 'Post Title' in list view
    column_labels = dict(title='Post Title')

    column_searchable_list = ('title', Type.name)

    column_filters = ('author',
                      'title',
                      'date',
                      filters.FilterLike(Post.title, 'Fixed Title', options=(('test1', 'Test 1'), ('test2', 'Test 2'))))

    # Pass arguments to WTForms. In this case, change label for text field to
    # be 'Big Text' and add required() validator.
    form_args = dict(
                    text=dict(label='Big Text', validators=[validators.required()])
                )



    def __init__(self, session):
        # Just call parent class with predefined model.
        super(PostAdmin, self).__init__(Post, session)

class EmailPreview(sqla.ModelView):
    def get_query(self):
        now = datetime.datetime.now()
        last_month = now - relativedelta(months=1)
        return self.session.query(self.model).filter(and_(Post.publish, Post.date <= now, Post.date >= last_month))

    def get_count_query(self):
        return self.session.query(func.count('*')).filter(Post.publish)

    def is_accessible(self):
        return login.current_user.is_authenticated()

    list_template = 'email_preview_list.html'

    @action('preview', '')
    def action_preview(self, ids):
        pass

    can_create = False
    can_edit = False
    can_delete = False
    list_row_actions_header = None
    column_descriptions = None

    # Visible columns in the list view
    column_exclude_list = ['text', 'publish', 'edit']

    # List of columns that can be sorted. For 'user' column, use User.username as
    # a column.
    column_sortable_list = ('type', 'title', 'author', 'date')

    # Rename 'title' columns to 'Post Title' in list view
    column_labels = dict(title='Post Title')

    column_searchable_list = ('title', Type.name)

    column_filters = ('author',
                      'title',
                      'date',
                      filters.FilterLike(Post.title, 'Fixed Title', options=(('test1', 'Test 1'), ('test2', 'Test 2'))))

    # Pass arguments to WTForms. In this case, change label for text field to
    # be 'Big Text' and add required() validator.
    form_args = dict(
                    text=dict(label='Big Text', validators=[validators.required()])
                )


class TypeAdmin(sqla.ModelView):

    def is_accessible(self):
        return login.current_user.is_authenticated()

    def __init__(self, session):
        super(TypeAdmin, self).__init__(Type, session)



class NewsletterAdmin(sqla.ModelView):

    def is_accessible(self):
        return login.current_user.is_authenticated()

    def __init__(self, session):
        super(NewsletterAdmin, self).__init__(Newsletter, session)


# Create customized index view class that handles login & registration
class MyAdminIndexView(admin.AdminIndexView):

    @expose('/')
    def index(self):
        if not login.current_user.is_authenticated():
            return redirect(url_for('.login_view'))
        return super(MyAdminIndexView, self).index()

    @expose('/login/', methods=('GET', 'POST'))
    def login_view(self):
        # handle user login
        form = LoginForm(request.form)
        if helpers.validate_form_on_submit(form):
            user = form.get_user()
            login.login_user(user)
        if login.current_user.is_authenticated():
            return redirect(url_for('.index'))
        self._template_args['form'] = form   
        return super(MyAdminIndexView, self).index()

        

    @expose('/logout/')
    def logout_view(self):
        login.logout_user()
        return redirect(url_for('.index'))



# Create admin
admin = admin.Admin(app, name='AACNews', index_view=MyAdminIndexView(), base_template='my_master.html')


# Add views
admin.add_view(TypeAdmin(db.session))
admin.add_view(NewsletterAdmin(db.session))
admin.add_view(PostAdmin(db.session))
admin.add_view(EmailPreview(Post, db.session, endpoint="email_preview", name='Email Preview'))


@app.route('/admin/email_preview_action', methods=['POST'])
def email_preview_action():
    title = request.form['title']
    spoiler = request.form['spoiler']
    preamble = request.form['preamble']
    ids = request.form.getlist('rowid')

    models = Post.query.filter(Post.id.in_(ids)).all()

    groups = defaultdict(list)
    for obj in models:
        groups[obj.type.name].append( obj )

    print groups

    posts_map = []
    for key in groups:
        entry = {}
        entry['type'] = key
        entry['posts'] = groups[key]
        posts_map.append(entry)


    m = get_mailchimp_api()
    elem = m.campaigns.list({ 'title' : app.config['MAILCHIMP_CAMPAIGN_NAME'], 'exact' : True })

    assert elem['total'] == 1

    cid = elem['data'][0]['id']
    html = m.campaigns.content(cid)['html']

    template = Template(html)
    html = template.render(preamble = preamble, title = title, spoiler = spoiler,
        posts_map = posts_map).replace('View this email in your browser', '')


    return render_template('email_preview_action.html', template_content = html)


def build_sample_db():
    """
    Populate a small db with some example entries.
    """

    import random
    import datetime

    db.drop_all()
    db.create_all()

    # Create sample Tags
    type_list = []
    for tmp in ["Videos", "Training", "Projects", "Software Updates", "Other"]:
        type = Type()
        type.name = tmp
        type_list.append(type)
        db.session.add(type)

    # Create sample Posts
    sample_text = [
        {
            'title': "de Finibus Bonorum et Malorum - Part I",
            'content': "Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor \
                        incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud \
                        exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure \
                        dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. \
                        Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt \
                        mollit anim id est laborum."
        },
        {
            'title': "de Finibus Bonorum et Malorum - Part II",
            'content': "Sed ut perspiciatis unde omnis iste natus error sit voluptatem accusantium doloremque \
                        laudantium, totam rem aperiam, eaque ipsa quae ab illo inventore veritatis et quasi architecto \
                        beatae vitae dicta sunt explicabo. Nemo enim ipsam voluptatem quia voluptas sit aspernatur \
                        aut odit aut fugit, sed quia consequuntur magni dolores eos qui ratione voluptatem sequi \
                        nesciunt. Neque porro quisquam est, qui dolorem ipsum quia dolor sit amet, consectetur, \
                        adipisci velit, sed quia non numquam eius modi tempora incidunt ut labore et dolore magnam \
                        aliquam quaerat voluptatem. Ut enim ad minima veniam, quis nostrum exercitationem ullam \
                        corporis suscipit laboriosam, nisi ut aliquid ex ea commodi consequatur? Quis autem vel eum \
                        iure reprehenderit qui in ea voluptate velit esse quam nihil molestiae consequatur, vel illum \
                        qui dolorem eum fugiat quo voluptas nulla pariatur?"
        },
        {
            'title': "de Finibus Bonorum et Malorum - Part III",
            'content': "At vero eos et accusamus et iusto odio dignissimos ducimus qui blanditiis praesentium \
                        voluptatum deleniti atque corrupti quos dolores et quas molestias excepturi sint occaecati \
                        cupiditate non provident, similique sunt in culpa qui officia deserunt mollitia animi, id \
                        est laborum et dolorum fuga. Et harum quidem rerum facilis est et expedita distinctio. Nam \
                        libero tempore, cum soluta nobis est eligendi optio cumque nihil impedit quo minus id quod \
                        maxime placeat facere possimus, omnis voluptas assumenda est, omnis dolor repellendus. \
                        Temporibus autem quibusdam et aut officiis debitis aut rerum necessitatibus saepe eveniet \
                        ut et voluptates repudiandae sint et molestiae non recusandae. Itaque earum rerum hic tenetur \
                        a sapiente delectus, ut aut reiciendis voluptatibus maiores alias consequatur aut perferendis \
                        doloribus asperiores repellat."
        }
    ]

    for user in tmp:
        entry = random.choice(sample_text)  # select text at random
        post = Post()
        post.title = entry['title']
        post.text = entry['content']
        post.author = 'willwade'
        tmp = int(1000*random.random())  # random number between 0 and 1000:
        post.date = datetime.datetime.now() - datetime.timedelta(days=tmp)
        post.type_id = 1     # select a couple of tags at random
        db.session.add(post)

    user = User()
    user.login = "willwade@gmail.com"
    user.password = "pass"

    db.session.add(user)
    
    db.session.commit()
    return

if __name__ == '__main__':
    # Build a sample db on the fly, if one does not exist yet.
    app_dir = op.realpath(os.path.dirname(__file__))
    database_path = op.join(app_dir, app.config['DATABASE_FILE'])
    if not os.path.exists(database_path):
        build_sample_db()

    # Start app
    app.run(debug=True)