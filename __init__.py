from mycroft import MycroftSkill, intent_file_handler


class MoodleQuiz(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

    @intent_file_handler('quiz.moodle.intent')
    def handle_quiz_moodle(self, message):
        self.speak_dialog('quiz.moodle')


def create_skill():
    return MoodleQuiz()

