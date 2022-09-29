from mycroft import MycroftSkill, intent_file_handler
from mycroft.util.parse import extract_number, fuzzy_match, extract_duration
import json
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import re
import datetime

class MoodleQuiz(MycroftSkill):
    def __init__(self):
        MycroftSkill.__init__(self)

    @intent_file_handler('quiz.moodle.intent')
    def handle_quiz_moodle(self, message):
        if (str(self.settings.get('domainname'))=="None" or str(self.settings.get('domainname'))=="" ):
            self.speak_dialog('nosettings')
            return
        token = self.get_token()
        courseid = int(self.settings.get('courseid'))
        # self.debug_tmp(courseid)
        if self.ask_yesno('quiz.moodle') != 'yes':
            return
        quiz_ids = self.quiz_num(courseid, token)
        if len(quiz_ids)<1:
            self.speak_dialog("noquiz", data={'courseid': courseid})
            return
        startquiz_str = "The number of quizzes is " + str(len(quiz_ids)) + ". Select one from number one to number " + str(len(quiz_ids)) + "."
        quizno = self.select_number(startquiz_str, 0, len(quiz_ids)-1)
        # self.quiz_attempt1(courseid, quiz_ids[quizno], token)

        # def quiz_attempt1(self, courseid, quiz_id, token):
        quiz_id = quiz_ids[quizno]
        attemptid = self.start_quiz_attempt(quiz_id, token)
        if attemptid == False:  # quiz in progress
           attemptid = self.get_user_attempt_unfinished(quiz_id, token)
        # self.speak_dialog("debug", data={'s': str(attemptid) } )
        resp = self.quiz_get_attempt_summary(attemptid, token)
        questions = self.getQuestions(ET.fromstring(resp.text)) # question を取得
        
        multichoicenum = 0;
        for question in questions:
            if question['type']=='multichoice':
                multichoicenum += 1
        if multichoicenum == 0:
            # echo "No multichoice questions."
            return
        count = 0
        for question in questions:
            if question['type']=='multichoice':
                count += 1
                sentence =  "Question " + str(count) + ": "
                sentence +=  self.getSentence(question['html']) # 問題文
                self.speak_dialog( "speech1", data={'speech1_str': sentence } )
                answers = self.getAnswers(question['html']) # 回答一覧
                answers_str = ""
                for anstmp in answers:
                    answers_str += 'Number ' + str(int(anstmp['value'])+1) + ': ' + anstmp['label'] + ". "
                ans_selected = self.select_number(answers_str, 0, len(answers)-1)
                answer = { 'name' : answers[ans_selected]['name'], 'value' : answers[ans_selected]['value'] }
                inputdata = []
                xmlObject = BeautifulSoup(question['html'], 'html.parser')
                for tag in xmlObject.find_all('input',type="hidden"):
                    if tag.get('name'):
                        inputdata.append( { 'name':tag['name'], 'value':tag['value'] } )
                inputdata.append(answer) # user's selection
                resp1 = self.save_quiz_attempt(attemptid, inputdata, token)
                # self.debug_tmp(resp1)
                tmp = "Your choice is number " + str(ans_selected+1)
                self.speak_dialog( "speech1", data={'speech1_str': tmp } )
        resp1 = self.process_quiz_attempt(attemptid, token) # テストを保存して終了
        self.debug_tmp(resp1)
        qresult = self.quiz_get_attempt_review(attemptid, token) # テスト結果
        # self.debug_tmp(str(qresult))
        marks_str= self.getMarks(qresult)
        self.speak_dialog( "speech1", data={'speech1_str': marks_str } )
        return

    
    def select_number(self, speech_str, min, max):
        self.speak_dialog("select_num", data={'speech_str': speech_str } )
        while True:
            ans1 = self.get_response("select_num", data={'speech_str': "Your choice?" }, num_retries=1)
            extracted_ordinal = self._extract_ordinal(ans1)
            if extracted_ordinal:
                ordinal, utt = extracted_ordinal
            else:
                ordinal = extracted_ordinal
            # self.debug_tmp(ans1)
            num_selected = ordinal-1
            if (num_selected < min or num_selected > max):
                self.speak_dialog("select_num", data={'speech_str': "Choose a valid number." } )
            else:
                return num_selected

            
    def start_quiz_attempt(self, quiz_id, token):
        # テストを開始する→これを実行すると、受験中になる。
        # すでに受験中の場合、エラーメッセージが返ってくる。

        domainname = self.settings.get('domainname')
        #restformat = '&moodlewsrestformat=json'        
        restformat = ''
        functionname = "mod_quiz_start_attempt";

        params1 =  { 'quizid' : quiz_id }

        serverurl = domainname + '/webservice/rest/server.php' + '?wstoken=' + token + '&wsfunction=' + functionname
        resp = requests.post(serverurl + restformat, params1)
        # self.debug_tmp(resp.text)

        if re.search(r'attemptstillinprogress',resp.text):
            return False
        # $attemptid = (string)$a_data->SINGLE->KEY[0]->SINGLE->KEY[0]->VALUE;

        #<KEY name="attempt"><VALUE>62</VALUE>
        #</KEY>

        data = ET.fromstring(resp.text)
        attemptid = data[0][0][0][0][0].text
        # self.debug_tmp(str(resp.text))
        # attemptid = data.SINGLE.KEY[0].SINGLE.KEY[0].VALUE
        return attemptid
        

    def save_quiz_attempt(self, attemptid, inputdata, token):
    # def save_quiz_attempt(self, payload):
        # テストを保存する（1問ずつ回答できる）
        domainname = self.settings.get('domainname')
        restformat = ''
        functionname = "mod_quiz_save_attempt"
        serverurl = domainname + '/webservice/rest/server.php' + '?wstoken=' + token + '&wsfunction=' + functionname

        params1 = { "attemptid" : int(attemptid) }
        for i in range(0,3):
            params1.update({
                f"data[{i}][name]"  : inputdata[i]['name'],
                f"data[{i}][value]" : inputdata[i]['value'] })

        # params1 = {'attemptid' : int(attemptid), 'data' : inputdata }
        # これでは、Invalid parameter value detected のエラー。
        # https://stackoverflow.com/questions/53161278/accessing-a-moodle-servers-api-via-pythons-request-library
        
        resp = requests.post(serverurl + restformat, params1)
        self.debug_tmp(params1)
        return resp

    
    def _extract_ordinal(self, text):  # from mycroft-timer.mycroftai
        """ Extract ordinal from text
        Remove once extract_number supports short ordinal format eg '2nd'
        """
        num = None
        if text is None or len(text) == 0:
            return None

        try:
            num = extract_number(text, self.lang, ordinals=True)
            # attempt to remove extracted ordinal
            spoken_ord = str(num)
            # spoken_ord = num2words(int(num), to="ordinal", lang=self.lang)
            utt = text.replace(spoken_ord,"")
        except:
            self.log.debug('_extract_ordinal: ' +
                          'Error in extract_number process')
            pass
        if not num:
            try:
                # Should be removed if the extract_number() function can
                # parse ordinals already e.g. 1st, 3rd, 69th, etc.
                regex = re.compile(r'\b((?P<Numeral>\d+)(st|nd|rd|th))\b')
                result = re.search(regex, text)
                if (result) and (result['Numeral']):
                    num = result['Numeral']
                    utt = text.replace(result,"")
            except:
                self.log.debug('_extract_ordinal: ' +
                              'Error in regex search')
                pass
        return (int(num), utt)


    def get_token(self):
        domainname = self.settings.get('domainname')
        username = self.settings.get('username')
        password = self.settings.get('password')
        servicename = "moodle_mobile_app"
        url = domainname + "/login/token.php?username=" + username + "&password=" + password + "&service=" + servicename
        html = requests.get(url)
        data = json.loads(html.text)
        token = data['token']
        return token


    def quiz_num(self, courseid, token):
        domainname = self.settings.get('domainname')
        #restformat = '&moodlewsrestformat=json'        
        restformat = ''
        functionname = "mod_quiz_get_quizzes_by_courses"
        params1 = ''

        serverurl = domainname + '/webservice/rest/server.php' + '?wstoken=' + token + '&wsfunction=' + functionname
        resp = requests.post(serverurl + restformat, params1)

        # $objtmp1 = $q_data->SINGLE->KEY[0]->MULTIPLE->SINGLE[$quizno];
        
        data = ET.fromstring(resp.text)[0][0][0]
        # data = json.loads(resp.text)
        # self.debug_tmp(data)
        
        quiznum = []
        for quizd in data:
            flag = False
            #qid  = ''
            for quizp in quizd:
                # print(quizp.attrib['name'], quizp[0].text, file=fileobj)
                if quizp.attrib['name'] == 'id':
                    qid = quizp[0].text
                if quizp.attrib['name'] == 'course' and int(quizp[0].text) == courseid:
                    flag = True
            if flag:
                quiznum.append(qid)
        #fileobj.close()
        return quiznum


    def get_user_attempt_unfinished(self, quiz_id, token):
        domainname = self.settings.get('domainname')
        #restformat = '&moodlewsrestformat=json'        
        restformat = ''
        functionname = "mod_quiz_get_user_attempts";

        params1 =  { 'quizid' : quiz_id, 'status' : 'unfinished' }

        serverurl = domainname + '/webservice/rest/server.php' + '?wstoken=' + token + '&wsfunction=' + functionname
        resp = requests.post(serverurl + restformat, params1)

        # $attemptid = (string)$a_data->SINGLE->KEY[0]->MULTIPLE->SINGLE->KEY[0]->VALUE;

        root = ET.fromstring(resp.text)
        '''
        <RESPONSE>
        <SINGLE>
        <KEY name="attempt"><SINGLE>
        <KEY name="id"><VALUE>2078</VALUE>
        </KEY>
        <KEY name="quiz"><VALUE>9</VALUE>
        </KEY>
        <KEY name="userid"><VALUE>10</VALUE>
        </KEY>
        <KEY name="attempt"><VALUE>62</VALUE>
        '''
        attemptid = root[0][0][0][0][0][0].text
        #attemptid = root[0][0][0][0][3][0].text
        # self.debug_tmp(attemptid)

        #attemptid = 0
        #for tmp in root.findall(".//*[@name='attempt']/VALUE"):
        # for tmp in root.findall('./RESPONSE/SINGLE/KEY/SINGLE/KEY[4]/VALUE'):
            #attemptid = tmp
        return str(attemptid)


    def quiz_get_attempt_summary(self, attemptid, token):
        domainname = self.settings.get('domainname')
        #restformat = '&moodlewsrestformat=json'        
        restformat = ''
        functionname = "mod_quiz_get_attempt_summary"        

        params1 =  { 'attemptid' : attemptid }
        serverurl = domainname + '/webservice/rest/server.php' + '?wstoken=' + token + '&wsfunction=' + functionname
        resp = requests.post(serverurl + restformat, params1)
        return resp

    def process_quiz_attempt(self, attemptid, token):
        domainname = self.settings.get('domainname')
        #restformat = '&moodlewsrestformat=json'        
        restformat = ''
        functionname = "mod_quiz_process_attempt";
        # timeup = 0;    // trueの場合は時間切れ扱い

        params1 =  { 'attemptid' : attemptid, 'finishattempt' : 1 }
        serverurl = domainname + '/webservice/rest/server.php' + '?wstoken=' + token + '&wsfunction=' + functionname
        resp = requests.post(serverurl + restformat, params1)
        return resp

    def quiz_get_attempt_review(self, attemptid, token):
        domainname = self.settings.get('domainname')
        #restformat = '&moodlewsrestformat=json'        
        restformat = ''
        functionname = "mod_quiz_get_attempt_review";
        page = 0;
        params1 =  { 'attemptid' : attemptid, 'page' : page }
        #params1 =  { 'attemptid' : attemptid }
        
        serverurl = domainname + '/webservice/rest/server.php' + '?wstoken=' + token + '&wsfunction=' + functionname
        resp = requests.post(serverurl + restformat, params1)
        return resp


    def getQuestions(self, xmlObject):
        questions = []
        # $tmpData = $xmlObject->SINGLE->KEY[0]->MULTIPLE->SINGLE;
        #self.debug_tmp(xmlObject)
        tmpData = xmlObject[0][0][0]
        for tmpItem in tmpData :
            question = {}
            question['slot']             = str(tmpItem[0][0].text)
            question['type']             = str(tmpItem[1][0].text)
            question['page']             = str(tmpItem[2][0].text)
            question['html']             = str(tmpItem[3][0].text)
            question['sequencecheck']    = str(tmpItem[4][0].text)
            question['lastactiontime']   = str(tmpItem[5][0].text)
            question['hasautosavedstep'] = str(tmpItem[6][0].text)
            question['flagged']          = str(tmpItem[7][0].text)
            question['number']           = str(tmpItem[8][0].text)
            question['state']            = str(tmpItem[9][0].text)
            question['status']           = str(tmpItem[10][0].text)
            question['blockedbyprevious'] = str(tmpItem[11][0].text)
            question['mark']             = str(tmpItem[12][0].text)
            question['maxmark']          = str(tmpItem[13][0].text)
            # $question['maxmark']           = (string)$tmpItem->KEY[13]->VALUE;
            #self.debug_tmp(question)
            questions.append(question)
        return questions


    def getSentence(self, html):
        result = ""

        xmlObject = BeautifulSoup(html, 'html.parser')
        # self.debug_tmp(html)
        # targetDOM = xmlObject.body.h1.string

        targetDOM = xmlObject.find('div',class_="qtext")
        # targetDOM = xmlObject.find_all('div',class_="qtext")
        # self.debug_tmp(targetDOM)

        # targetDOM = xmlObject->body->div->div[1]->div[0]->div[0]->p;
        # $targetDOM = $xmlObject->body->div->div[1]->div[0]->div[0]->p;

        # $result = (string)$targetDOM[0].(string)$targetDOM[1];
        # $result = (string)$targetDOM->main->article->div->div->saveXML(); # タグ付きで保存する場合
        # result = str(targetDOM.p.string)
        result = str(targetDOM)
        return result


    def getAnswers(self, html):
        xmlObject = BeautifulSoup(html, 'html.parser')
        targetDOM = xmlObject.find('div',class_="answer").contents
        # targetDOM = xmlObject->body->div->div[1]->div[0]->div[1];
        # xmlObject2 = BeautifulSoup(str(targetDOM), 'html.parser')
        # targetDOM2 = xmlObject2.find_all('div')
        #self.debug_tmp(str(targetDOM))
        answers = []
        for div in targetDOM:
            item = {}
            xmlObject2 = BeautifulSoup(str(div), 'html.parser')
            DOM = xmlObject2.find('div', class_="flex-fill")
            if (str(DOM) != 'None'):
                #self.debug_tmp(str(DOM))
                item['name']   = xmlObject2.div.input["name"]
                item['value']  = xmlObject2.div.input["value"]
                item['label']  = str(xmlObject2.div.div.div)
                # self.debug_tmp(str(xmlObject2.div.div.div))
                # item['label']  = str(DOM)
                answers.append(item)
                # $item->name = (string)$value->input->attributes()->name;
        return answers


    def getMarks(self, resp):
        root = ET.fromstring(resp.text)
        #self.debug_tmp(resp.text)
        #param1 = root[0][0][0][0][0][0].text

        '''
        still much to todo like :
  $xmlObject = simplexml_load_string($xml);
  $targetDOM = $xmlObject->SINGLE->KEY[3]->MULTIPLE;
  $co = 0;
  foreach ($targetDOM->SINGLE as $tdom){
    $co++;
    foreach ($tdom->KEY as $tmp) {
      if ( (string)$tmp->attributes()->name == "mark" ){
        $mark = (string)$tmp->VALUE;
      }
      if ( (string)$tmp->attributes()->name == "maxmark" ){
        $maxmark = (string)$tmp->VALUE;
      }
      if ( (string)$tmp->attributes()->name == "html" ){
        $html = (string)$tmp->VALUE;
        $xmlObject = convHtml($html);
        $targetDOM = $xmlObject->body->div->div[1]->div[0]->div[1];
        $specificfeedback = "";
        foreach ($targetDOM->div[1] as $value) { // for each answer item
          if( (string)$value->input->attributes()->checked == "checked" ){
            // $checkedanswer= (string)$value->label;
            if ( (string)$value->div->attributes()->class == "specificfeedback" ){
              $specificfeedback = (string)$value->div;
            }
          } 
        }
      }
      if ( (string)$tmp->attributes()->name == "status" ){
        $status = (string)$tmp->VALUE;
      }
    }
      $result .= " Quiz #".$co.": ";
      if ($status == "Correct"){
        $result .=  '<audio src=\"soundbank://soundlibrary/ui/gameshow/amzn_ui_sfx_gameshow_positive_response_02\"/>' . "$status . $specificfeedback . ";
      }else if ($status == "Incorrect"){
        $result .=  '<audio src=\"soundbank://soundlibrary/ui/gameshow/amzn_ui_sfx_gameshow_negative_response_02\"/>' . "$status . $specificfeedback . ";
      }else{
        $result .= "the score is $mark out of $maxmark points, which means $status . $specificfeedback . ";
    }
  }
        '''
        if (resp.text.find('Incorrect')>0):
            return "Your answer is incorrect. This is the end of the quiz."
        else:
            return "Your answer is correct. This is the end of the quiz."


    def debug_tmp(self, str0):
        file = "/tmp/tt.txt"
        fileobj = open(file, "a", encoding = "utf_8")
        # fileobj.write(str0)
        print(datetime.datetime.now().isoformat(), file=fileobj)
        print(str0, file=fileobj)
        print("------------------------\n", file=fileobj)
        print(type(str0), file=fileobj)
        if not type(str0) is str:
            for str1 in str0:
                print(str1, file=fileobj)
        fileobj.close()
        return


def create_skill():
    return MoodleQuiz()
