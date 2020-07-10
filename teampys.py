import io
from flask import Flask
from flask import request
from flask import redirect
from flask import render_template
from flask import send_file
import uuid
import random
import string
import json
from flask_pymongo import *
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from itsdangerous import URLSafeSerializer

app = Flask(__name__)


############  Mongo DB section/connection ################
app.config['SECRET_KEY'] = 'Hemmelig!'  ## is required
app.config["MONGO_DBNAME"] = "ratdb"  ## DB name
app.config["MONGO_URI"] = "mongodb://localhost:27017/ratdb"   ## local DB, But can be used MLab(free 500MB) https://mlab.com/

mongo = PyMongo(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
serializer = URLSafeSerializer(app.secret_key)

class User(UserMixin):
    def __init__(self, user_data):
        self.user_data = user_data

    def get_id(self):
        return self.user_data['session_token']

@login_manager.user_loader
def load_user(session_token):
    ratdb = mongo.db.ratdb 
    user_data = ratdb.find_one({'session_token': session_token})
    if user_data:
        return Teacher(user_data)
    return None

############## End of DB section  ###############
# all scratchcards
cards = {}

# teacher UUID to RAT
rats_by_private_id = {}

# student access to RAT
rats_by_public_id = {}

colors = ['STEELBLUE', 'CADETBLUE', 'LIGHTSEAGREEN', 'OLIVEDRAB', 
    'YELLOWGREEN', 'FORESTGREEN', 'MEDIUMSEAGREEN', 'LIGHTGREEN', 
    'LIMEGREEN', 'DARKMAGENTA', 'DARKORCHID', 'MEDIUMORCHID', 'ORCHID', 
    'ORANGE', 'ORANGERED', 'CORAL', 'LIGHTSALMON', 'PALEVIOLETRED', 
    'MEDIUMVIOLETRED', 'DEEPPINK', 'CRIMSON', 'SALMON']

class AnswerState():
    def __init__(self, question, symbol, correct=False, uncovered=False):
        self.question = question
        self.symbol = symbol
        self.correct = correct
        self.uncovered = uncovered
    
    def html(self):
        s = []
        if self.uncovered:
            if self.correct:
                s.append('<div class="btn-group" role="group">')
                s.append('<a class="answer btn btn-secondary btn-success disabled">')
                s.append('<svg class="bi bi-check-circle-fill" width="1em" height="1em" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg">')
                s.append('<path fill-rule="evenodd" d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zm-3.97-3.03a.75.75 0 0 0-1.08.022L7.477 9.417 5.384 7.323a.75.75 0 0 0-1.06 1.06L6.97 11.03a.75.75 0 0 0 1.079-.02l3.992-4.99a.75.75 0 0 0-.01-1.05z"/>')
                s.append('</svg>')
                s.append('</a>')
                s.append('</div>')
            else:
                s.append('<div class="btn-group" role="group">')
                s.append('<a class="answer btn btn-secondary btn-success disabled">&nbsp;</a>')
                s.append('</div>')
        else:
            if self.question.finished:
                s.append('<div class="btn-group" role="group">')
                s.append('<a class="answer btn btn-secondary disabled">&nbsp;</a>')
                s.append('</div>')
            else:
                url = './?question={}&alternative={}'.format(self.question.number, self.symbol)
                s.append('<div class="btn-group" role="group">')
                s.append('<a class="answer btn btn-secondary" href="{}">&nbsp;</a>'.format(url))
                s.append('</div>')
        return ''.join(s)

class Question():
    def __init__(self, number, correct_alternative, alternatives=4):
        self.number = number
        self.finished = False
        self.started = False
        self.correct_on_first_attempt = False
        self.first_guess = None
        self.answers = {}
        for symbol in 'ABCDEFGH'[:alternatives]:
            correct = symbol.lower() == correct_alternative.lower()
            self.answers[symbol] = AnswerState(self, symbol, correct=correct)
    
    def html(self):
        s = []
        s.append('<tr>')
        s.append('<td>{}</td>'.format(self.number))
        for a in self.answers.values():
            s.append('<td>')
            s.append(a.html())
            s.append('</td>')
        s.append('</tr>')
        return ''.join(s)

    def uncover(self, alternative):
        answer_state = self.answers[alternative]
        answer_state.uncovered = True
        if not self.started:
            self.first_guess = alternative
            if answer_state.correct:
                self.correct_on_first_attempt = True
        if answer_state.correct:
            self.finished = True
        self.started = True
        
    def get_state(self):
        if self.correct_on_first_attempt:
            return 'OK'
        elif self.started:
            return self.first_guess
        return ''

    def get_state_string_export(self):
        if self.started:
            return self.first_guess
        return '-'

class Card():

    def __init__(self, id, label, team, questions, alternatives, solution, color):
        self.id = id
        self.label = 'Team Quiz' if label is None else label
        self.team = team
        self.questions = questions
        self.alternatives = alternatives
        self.solution = solution
        self.color = color


    @staticmethod
    def new_card(label, team, questions, alternatives, solution, color):
        id = '{}'.format(uuid.uuid4())
        questions = {}
        for index, c in enumerate(solution):
            questions[str(index+1)] = Question(index+1, c, alternatives=alternatives)
        return Card(id, label, team, questions, alternatives, solution, color)

    def uncover(self, question, alternative):
        print('uncover {} {}'.format(question, alternative))
        question = self.questions[str(question)]
        question.uncover(alternative)

    def get_card_html(self, base_url):
        s = []
        s.append('<table width="100%">')
        s.append('<thead>')
        s.append('<tr>')
        s.append('<th></th>')
        for symbol in 'ABCDEFGH'[:self.alternatives]:
            s.append('<th>{}</th>'.format(symbol))
        s.append('</tr>')
        s.append('</thead>')
        s.append('<tbody>')
        for q in self.questions.values():
            s.append(q.html())
        s.append('</tbody>')
        s.append('</table>')
        url = base_url + 'card/' + self.id
        return render_template('card.html', table=''.join(s), label=self.label, team=self.team, url=url, primary=self.color)

    def get_link(self):
        return 'card/{}'.format(self.id)

    def get_state(self):
        started = False
        finished = True
        for q in self.questions.values():
            if q.started:
                started = True
            if not q.finished:
                finished = False
        if finished:
            return 'finished'
        elif started:
            return 'ongoing'
        return 'idle'

    def get_score(self):
        score = 0
        for q in self.questions.values():
            if q.correct_on_first_attempt:
                score = score + 1
        return score

    def get_table_row(self, base_url):
        s = []
        s.append('<tr>')
        url = base_url + 'card/' + self.id 
        s.append('<th scope="row"><a href="{}">{}</a></th>'.format(url, self.team))
        s.append('<td>{}</td>'.format(self.get_state()))
        s.append('<td>{}</td>'.format(self.get_score()))
        for q in self.questions.values():
            s.append('<td>{}</td>'.format(q.get_state()))
        s.append('</tr>')
        return ''.join(s)

    def get_text_result(self):
        s = []
        s.append('{}/'.format(self.team))
        for q in self.questions.values():
            s.append('{}'.format(q.get_state_string_export()))
        return ''.join(s)

class RAT():

    def __init__(self, private_id, public_id, label, teams, questions, alternatives, solution, team_colors):
        self.private_id = private_id
        self.public_id = public_id
        self.label = label
        self.teams = int(teams)
        self.questions = questions
        self.alternatives = alternatives
        self.solution = solution
        self.card_ids_by_team = {}
        self.grabbed_rats = []
        self.team_colors = team_colors
        
    
    def get_status_table(self, base_url):
        s = []
        s.append('<table class="table table-sm">')
        s.append('<thead>')
        s.append('<tr>')
        s.append('<th scope="col">Team</th>')
        s.append('<th scope="col">Status</th>')
        s.append('<th scope="col">Score</th>')
        for q in range(1, int(self.questions) + 1, 1):
            s.append('<th scope="col">{}</th>'.format(q))
        s.append('</tr>')
        s.append('</thead>')
        s.append('<tbody>')
        global cards
        for card_id in self.card_ids_by_team.values():
            card = cards[card_id]
            s.append(card.get_table_row(base_url))
        s.append('</tbody>')
        s.append('</table>')
        return ''.join(s)

    def html_teacher(self, base_url):
        s = []
        public_url = base_url + 'rat/{}'.format(self.public_id)
        private_url = base_url + 'teacher/{}'.format(self.private_id)
        download_url = base_url + 'download/{}'.format(self.private_id)
        return render_template('rat_teacher.html', public_url=public_url, private_url=private_url, table=self.get_status_table(base_url), download_url=download_url)

    def html_students(self, base_url):
        s = []
        for team in range(1, self.teams + 1, 1):
            # /grab/<public_id>/<team>
            url = base_url + 'grab/{}/{}'.format(self.public_id, team)
            s.append('<li class="col mb-4"><a class="" href="{}"><div class="name text-decoration-none text-center pt-1 team" style="background-color: {}">Team {}</div></a></li>'.format(url, self.team_colors[team-1], team))
        return render_template('rat_students.html', teams=''.join(s), url=base_url, public_id=self.public_id)

    def grab(self, team):
        if team in self.grabbed_rats:
            return None
        else:
            self.grabbed_rats.append(team)
            # TODO check if team exists
            return self.card_ids_by_team[team]
    
    def download(self, format):
        global cards
        if format == "string":
            s = []
            for card_id in self.card_ids_by_team.values():
                card = cards[card_id]
                s.append(card.get_text_result())
            return send_file(io.BytesIO('\n'.join(s).encode('utf-8')),
                     attachment_filename='trat.txt',
                     as_attachment=True,
                     mimetype='text/text')


@app.route('/')
def index():
    action_url = request.host_url + 'join'
    return render_template('start.html', primary='#007bff', action_url=action_url)

def return_student_page(public_id):
    global rats_by_public_id
    if public_id in rats_by_public_id:
        rat = rats_by_public_id[public_id]
        return rat.html_students(request.host_url)
    return "Could not find rat"

@app.route('/join', methods=['POST', 'GET'])
def join():
    rats= mongo.db.rats
    rat = request.args['rat']    
    rats.insert_one(rat)
        
    return return_student_page(rat)

@app.route('/rat/<public_id>/')
def show_rat_students(public_id):
    return return_student_page(public_id)

@app.route('/new/', methods=['POST', 'GET'])
def new():
    action_url = request.host_url + 'create'
    return render_template('new_rat.html', primary='#007bff', action_url=action_url)

def validate_solution(solution, questions, alternatives):
    valid_alternatives = 'ABCDDEFGH'[:alternatives]
    if len(solution) != questions:
        return 'You specified {} questions, but provided {} solution alternatives.'.format(questions, len(solution))
    for c in solution.upper():
        if c not in valid_alternatives:
            return 'The letter {} is not a valid solution with {} alternatives.'.format(c, alternatives)
    return None # all okay

@app.route('/create', methods=['POST', 'GET'])
def create():
    label = request.args['label'] if 'label' in request.args else None
    teams = int(request.args['teams'])
    questions = int(request.args['questions'])
    alternatives = int(request.args['alternatives'])
    solution = request.args['solution']
    message = validate_solution(solution, questions, alternatives)
    if message is not None:
        return message
    app.logger.debug('Create new RAT label: {}, teams: {}, questions: {}, alternatives: {}, solution: {}'.format(label, teams, questions, alternatives, solution))
    private_id = '{}'.format(uuid.uuid4())
    public_id = ''.join(random.choices(string.ascii_uppercase, k=5))
    team_colors = random.sample(colors, teams) 
    rat = RAT(private_id, public_id, label, teams, questions, alternatives, solution, team_colors)
    global rats_by_private_id
    global rats_by_public_id
    rats_by_private_id[private_id] = rat
    rats_by_public_id[public_id] = rat
    # create a new card for each team
    global cards
    for team in range(1, int(teams) + 1, 1):
        card = Card.new_card(label, str(team), int(questions), int(alternatives), solution, rat.team_colors[team-1])
        cards[card.id] = card
        rat.card_ids_by_team[str(team)] = card.id
        ratdb = mongo.db.ratdb
        session_token = serializer.dumps(['User', 'password'])
        card = [label, teams, questions, alternatives, solution]
        ratdb.insert_one({'card':card})
               
    return redirect("../teacher/{}".format(rat.private_id), code=302)

@app.route('/teacher/<private_id>/')
def show_rat_teacher(private_id):    
    global rats_by_private_id
    global rats_by_public_id    
    if private_id in rats_by_private_id:
        rat = rats_by_private_id[private_id]
        ratdb = mongo.db.ratdb
        session_token = serializer.dumps(['User', 'password'])
        #rat_data= RAT(private_id, public_id, label, teams, questions, alternatives, solution, team_colors)
        rat_data = [ rat.html_teacher(request.host_url)]
        ratdb.insert_one({'rat_data':rat_data}) 
        return rat.html_teacher(request.host_url)
    return "Could not find rat. Currently there are {} RATs stored.".format(len(rats_by_private_id))

@app.route('/card/<id>/')
def show_card(id):
    global cards
    if id in cards:
        card = cards[id]
        # check if the page request also answers a question
        if ('question' in request.form): # and ('alternative' in request.form):
            question = request.form['question']
            alternative = request.form['alternative']
            card.uncover(question, alternative)
        if ('question' in request.args): # and ('alternative' in request.form):
            question = request.args['question']
            alternative = request.args['alternative']
            card.uncover(question, alternative)
        return card.get_card_html(request.host_url)
    else:
        return "Could not find rat {}".format(rats_by_public_id)

@app.route('/grab/<public_id>/<team>')
def grab_rat_students(public_id, team):
    global rats_by_public_id
    app.logger.debug(rats_by_public_id)
    app.logger.debug(public_id)
    if public_id not in rats_by_public_id:
        return "Could not find rat {}".format(rats_by_public_id)
    else:
        rat = rats_by_public_id[public_id]
        card_id = rat.grab(team)
        if card_id is None:
            return 'Somebody already grabbed that card.'
        else:
            global cards
            if card_id in cards:
                return redirect("../../card/{}".format(card_id), code=302)
            else:
                return "Could not find card with ID {}".format(card_id)

@app.route('/download/<private_id>/<format>/')
def download(private_id, format):
    print('x')
    global rats_by_private_id
    if private_id in rats_by_private_id:
        rat = rats_by_private_id[private_id]
        return rat.download(format)
    return "Could not find rat. Currently there are {} RATs stored.".format(len(rats_by_private_id))

############  DATA COllECTION  ###############

@app.route('/data')
def data():


    return render_template ('data.html')

# @app.route('/data/<private_id>/')
# def data(private_id, **kwargs):
#     global rats_by_private_id
#     if private_id in rats_by_private_id:
#         rat = rats_by_private_id[private_id] 
#         return ('data.html', rat.html_teacher(request.host_url,**kwargs))
#         #return render_template('data.html', rat.html_teacher(request.host_url))


if __name__=="__main__":
    app.run(debug=True)