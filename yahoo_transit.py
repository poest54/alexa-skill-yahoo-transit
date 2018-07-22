# coding: UTF-8
"""
Amazon Alexa Skill: Yahoo Transit
Yahoo!路線情報を利用して、電車検索を行う。
"""

from __future__ import print_function

# -- Use KMS to encrypt IFTTT webhook key
import boto3
import os
from base64 import b64decode

import re
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup


# --------------------------------------
# -- グローバル変数
# --------------------------------------

# -- Yahoo!路線情報
GV_BASE_URL = 'https://transit.yahoo.co.jp'
GV_SEARCH_URL = 'https://transit.yahoo.co.jp/search/result'

# -- Line Notify via IFTTT
ENCRYPTED = os.environ['ifttt_webhook_key']
# Decrypt code should run once and variables stored outside of the function
# handler so that these are decrypted once per container
DECRYPTED = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED))['Plaintext'].decode('utf-8')
GV_IFTTT_URL = 'https://maker.ifttt.com/trigger/yahoo_transit/with/key/' + DECRYPTED

# -- 検索リクエストに含めるGETパラメータ
# -- タイプ: type = 1(出発), 2(終電), 3(始発), 4(到着)
GV_TYPE_DEPARTURE = 1
GV_TYPE_LAST = 2
GV_TYPE_FIRST = 3
GV_TYPE_ARRIVE = 4
# -- 歩く速度: ws = 1(急いで), 2(少し急いで), 3(少しゆっくり), 4(ゆっくり)
GV_WALK_SPEED = 2

# -- Alexaメッセージ
GV_MSG_PROMPT1 = 'Yahoo路線を使ってルート案内します。出発駅と到着駅を教えてください。'
GV_MSG_REPROMPT1 = '確認できませんでした。もう一度、渋谷駅から東京駅まで、のように出発駅と到着駅を教えてください。'
GV_MSG_PROMPT2 = '日時を教えてください'
GV_MSG_REPROMPT2 = '確認できませんでした。もう一度、今日の8時45分に到着、や、30分後に出発、や、' + \
                   '6月1日の始発、のように、出発または到着の日時を教えてください'
GV_MSG_PROMPT3 = '検索しています。お待ちください。'
GV_MSG_REPROMPT3 = '確認できませんでした。もう一度お試しください。'
GV_MSG_PROMPT_LAST = '前後の電車を検索する場合は、前の電車、または、次の電車と、' + \
                     '検索条件を変更する場合は、出発駅と到着駅、または、日時を言ってください。'
GV_MSG_EXIT = 'ハバッナイスデーイ！'
GV_MSG_ERROR = '確認できませんでした。再度お試しください。'
GV_MSG_ERROR_EXIT = '問題が発生しました。もう一度はじめからやり直してください。'


# --------------- Helpers that build all of the responses ----------------------

def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': "SessionSpeechlet - " + title,
            'content': "SessionSpeechlet - " + output
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }


def build_response(session_attributes, speechlet_response):
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }


# --------------- Functions that control the skill's behavior ------------------

def get_welcome_response():
    """ If we wanted to initialize the session to have some attributes we could
    add those here
    """
    session_attributes = {}
    card_title = 'Welcome'
    should_end_session = False

    speech_output = GV_MSG_PROMPT1
    # If the user either does not reply to the welcome message or says something
    # that is not understood, they will be prompted again with this text.
    reprompt_text = GV_MSG_REPROMPT1

    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def handle_session_end_request():
    card_title = 'Session Ended'
    speech_output = GV_MSG_EXIT
    # Setting this to true ends the session and exits the skill.
    should_end_session = True
    return build_response({}, build_speechlet_response(
        card_title, speech_output, None, should_end_session))


def handle_error_exit(session):
    card_title = 'Error Exit'
    speech_output = GV_MSG_ERROR_EXIT
    # Setting this to true ends the session and exits the skill.
    should_end_session = True
    return build_response({}, build_speechlet_response(
        card_title, speech_output, None, should_end_session))


def fetch_transit_info(station_from, station_to, search_date_time, search_type, walk_speed=GV_WALK_SPEED):
    """Yahoo路線のWebサイトで、指定した条件で路線情報を検索し、検索結果ページから路線情報を取得する。

    Parameters
    ----------
    station_from : str
        出発駅。
    station_to : str
        到着駅。
    search_date_time : str
        yyyy-mm-dd HH:MM形式の日時文字列。
    search_type : str
        '出発', '到着', '始発', '終電'
    walk_speed : int, default GV_WALK_SPEED
        歩く速度（1, 2, 3, 4）。

    Returns
    -------
    transit_info : dict
        路線情報。

    See Also
    --------
    parse_transit_info : 検索結果ページから最初に見つかった路線情報を抽出する。
    """
    dt = re.split('[- :]', search_date_time)
    if search_type == '出発':
        search_type_code = GV_TYPE_DEPARTURE
    elif search_type == '到着':
        search_type_code = GV_TYPE_ARRIVE
    elif search_type == '始発':
        search_type_code = GV_TYPE_FIRST
    elif search_type == '終電':
        search_type_code = GV_TYPE_LAST
    else:
        search_type_code = GV_TYPE_ARRIVE

    payload = {
        'from': station_from,
        'to': station_to,
        'y': dt[0],
        'm': dt[1],
        'd': dt[2],
        'hh': dt[3],
        'm2': dt[4][1],
        'm1': dt[4][0],
        'type': search_type_code,
        'expkind': 1,
        'ws': walk_speed,
        's': 0,
        'lb': 1,
        'kw': station_to
    }
    res = requests.get(GV_SEARCH_URL, params=payload)
    transit_info = parse_transit_info(res.content)
    # 直後の検索で利用する場合があるため、以下の項目をセット
    if transit_info is not None:
        transit_info['stationFrom'] = station_from
        transit_info['stationTo'] = station_to
        transit_info['searchDateTime'] = search_date_time
        transit_info['searchType'] = search_type
        transit_info['url'] = res.url

    return transit_info


def fetch_adjacent_transit_info(url, operation='next'):
    """引数で渡された URL（Yahoo路線の検索結果ページ）から、
    "一本前"または"一本後"の路線情報を検索し、検索結果ページから路線情報を取得する。

    Parameters
    ----------
    url : str
        直前でフェッチしたYahoo路線検索結果ページのURL。
    operation : str, default='next'
        一本後の電車の場合 "next"、一本前の電車の場合 "prev" を指定

    Returns
    -------
    transit_info : dict
        路線情報。

    See Also
    --------
    parse_transit_info : 検索結果ページから最初に見つかった路線情報を抽出する。
    """
    res = requests.get(url)
    soup = BeautifulSoup(res.content, 'html.parser')

    next_url = soup.find(class_=operation).a.get('href')
    res = requests.get(GV_BASE_URL + next_url)
    transit_info = parse_transit_info(res.content)

    # 直後の検索で利用する場合があるため、以下の項目をセット
    if transit_info is not None:
        transit_info['url'] = res.url

    return transit_info


def parse_transit_info(page):
    """検索結果ページから、最初に見つかった路線情報を抽出する。

    Parameters
    ----------
    page : str
        直前でフェッチしたYahoo路線検索結果ページのHTMLソース。

    Returns
    -------
    transit_info : dict
        路線情報。
    """
    transit_info = {}
    soup = BeautifulSoup(page, 'html.parser')
    try:
        route_detail = soup.find(class_='routeDetail')
        transit_info['distance'] = soup.find(class_='distance').get_text()
        transit_info['fare'] = soup.find(class_='fare').get_text()
        transit_info['transfer'] = re.search(r'\d', soup.find(class_='transfer').get_text())[0]
        transport = [
            line for line in
            re.split(r'\r\n|\r|\n', route_detail.get_text()) if re.match(r'\[train\]|\[bus\]', line)
        ][0]
        transit_info['transport'] = re.split(r'\]', transport)[1]
        transit_info['startTime'] = route_detail.find(class_='time').li.string
        transit_info['arrivalTime'] = route_detail.find_all(class_='time')[-1].li.string
    except:
        transit_info = None
        print('[ERR] Can not parse current pages.')

    return transit_info


def make_transit_message(transit_info):
    """路線情報に関するAlexa応答メッセージを生成する。

    Parameters
    ----------
    transit_info : dict
        路線情報。

    Returns
    -------
    msg : str
        Alexa応答メッセージ。
    """
    if transit_info is not None:
        msg = \
            transit_info['startTime'] + 'に' + transit_info['stationFrom'] + 'を発車する、' + \
            transit_info['transport'] + 'に乗車すると、' + transit_info['arrivalTime'] + 'に' + \
            transit_info['stationTo'] + 'に到着します。' + \
            '料金は' + transit_info['fare'] + 'で、' + transit_info['transfer'] + '回の乗り換えがあります。'
        msg = msg.replace('行に', '行きに').replace('0回の乗り換えがあります。', '乗り換えはありません。')
    else:
        msg = GV_MSG_ERROR
    return msg


def update_session_attributes(session_attributes, transit_info):
    """第1引数の既存セッションに、第2引数の路線情報（検索条件、検索結果）を追加・上書きする。

    Parameters
    ----------
    session_attributes : dict
        既存のセッション情報。
    transit_info : dict
        路線情報（検索条件、検索結果）
    """
    save_keys = ['stationFrom', 'stationTo', 'url', 'searchDateTime', 'searchType', 'searchResult']
    for key in save_keys:
        session_attributes[key] = transit_info.get(key)


def intent_SetStation(intent, session):
    """インテント[SetStation]
    ①出発駅、到着駅をセッションに保存する。
    """
    card_title = intent['name']
    should_end_session = False
    session_attributes = session['attributes'] if 'attributes' in session else {}

    try:
        # 検索条件をセッションに保存
        station_from = intent['slots']['StationFrom']['value']
        station_to = intent['slots']['StationTo']['value']
        transit_info = {
            'stationFrom': station_from,
            'stationTo': station_to}
        update_session_attributes(session_attributes, transit_info)

        # 次の検索条件を質問
        speech_output = GV_MSG_PROMPT2
        reprompt_text = GV_MSG_REPROMPT2
    except:
        # 現在の検索条件を再度質問
        speech_output = GV_MSG_ERROR
        reprompt_text = GV_MSG_PROMPT1

    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def convert_duration_to_datetime(duration):
    """現在時刻から指定した期間が経過した後の日時(文字列)を返す。
    期間は時、分のみを変換処理し、変換できない場合は現在日時を返す。

    Parameters
    ----------
    duration : str
        ISO-8601期間形式(PnYnMnDTnHnMnS)の期間。

    Returns
    -------
    converted_datetime : str
        yyyy-mm-dd HH:MM形式の日時文字列。
    """
    delta_hours = re.sub(r'^P.*T(\d+)H.*', r'\1', duration)
    delta_minutes = re.sub(r'^P.*[TH](\d+)M.*', r'\1', duration)

    converted_datetime = datetime.now(timezone(timedelta(hours=+9), 'JST'))
    if delta_hours[0] != 'P':
        converted_datetime = converted_datetime + timedelta(hours=int(delta_hours))
    if delta_minutes[0] != 'P':
        converted_datetime = converted_datetime +  timedelta(minutes=int(delta_minutes))

    return converted_datetime.strftime('%Y-%m-%d %H:%M')


def intent_SetDateTime(intent, session):
    """インテント[SetDateTime]
    ②日時、タイプ（出発／到着）をセッションに保存し、
    ここまでの検索条件で路線情報を検索する。
    """
    card_title = intent['name']
    should_end_session = False
    session_attributes = session['attributes'] if 'attributes' in session else {}

    try:
        # 検索条件を設定
        if 'value' in intent['slots']['Date']:
            search_date = intent['slots']['Date']['value']

            # 例）2018-06-01 の 23:59 に到着
            if 'value' in intent['slots']['Time']:
                search_time = intent['slots']['Time']['value']
            # 例）2018-06-01 の始発
            else:
                search_time = '00:00'

            search_date_time = search_date + ' ' + search_time
        else:
            # 例）30分後に出発
            search_date_time = convert_duration_to_datetime(intent['slots']['Duration']['value'])

        search_type = intent['slots']['Type']['value']

        # 路線情報を検索し、検索結果テキストを生成
        station_from = session_attributes['stationFrom']
        station_to = session_attributes['stationTo']
        transit_info = fetch_transit_info(station_from, station_to, search_date_time, search_type, GV_WALK_SPEED)
        speech_output = make_transit_message(transit_info)
        reprompt_text = GV_MSG_PROMPT_LAST

        # 検索結果をセッションに保存
        if transit_info is not None:
            transit_info['searchResult'] = speech_output
            update_session_attributes(session_attributes, transit_info)
        else:
            raise Exception
    except:
        # 現在の検索条件を再度質問
        speech_output = GV_MSG_ERROR
        reprompt_text = GV_MSG_PROMPT2

    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def intent_NextPrevious(intent, session, operation='next'):
    """インテント[AMAZON.NextIntent / Amazon.PreviousIntent]
    ③１本前(previous)または１本後(next)の路線情報を検索する
    """
    card_title = intent['name']
    should_end_session = False
    session_attributes = session['attributes'] if 'attributes' in session else {}

    try:
        # 路線情報を検索し、検索結果テキストを生成
        url = session_attributes['url']
        transit_info = fetch_adjacent_transit_info(url, operation)
        transit_info['stationFrom'] = session_attributes['stationFrom']
        transit_info['stationTo'] = session_attributes['stationTo']
        speech_output = make_transit_message(transit_info)
        reprompt_text = GV_MSG_PROMPT_LAST

        # 検索結果をセッションに保存
        if transit_info is not None:
            transit_info['searchResult'] = speech_output
            update_session_attributes(session_attributes, transit_info)
        else:
            raise Exception
    except:
        speech_output = GV_MSG_ERROR
        reprompt_text = GV_MSG_REPROMPT3

    # Setting reprompt_text to None signifies that we do not want to reprompt
    # the user. If the user does not respond or says something that is not
    # understood, the session will end.
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def intent_Repeat(intent, session):
    """インテント[AMAZON.RepeatIntent]
    ④直前の路線情報結果を返す
    """
    card_title = intent['name']
    should_end_session = False
    session_attributes = session['attributes'] if 'attributes' in session else {}

    try:
        # セッションに保存されている路線情報の検索結果テキストを取り出す
        speech_output = session_attributes['searchResult']
        reprompt_text = GV_MSG_PROMPT_LAST
    except:
        speech_output = GV_MSG_ERROR
        reprompt_text = GV_MSG_REPROMPT3

    # Setting reprompt_text to None signifies that we do not want to reprompt
    # the user. If the user does not respond or says something that is not
    # understood, the session will end.
    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def intent_CheckCondition(intent, session):
    """インテント[CheckCondition]
    ⑤検索条件を確認する
    """
    card_title = intent['name']
    should_end_session = False
    session_attributes = session['attributes'] if 'attributes' in session else {}

    # 路線情報を確認
    speech_output = '検索条件は、'
    station_from = session_attributes.get('stationFrom')
    station_to = session_attributes.get('stationTo')
    if station_from is not None and station_to is not None:
        speech_output = speech_output + station_from + 'から、' + station_to + 'まで、'
        reprompt_text = GV_MSG_PROMPT2

        search_date_time = session_attributes.get('searchDateTime')
        search_type = session_attributes.get('searchType')
        if search_date_time is not None and search_type is not None:
            search_date_time = re.sub(r'(\d+)-(\d+)-(\d+) (\d+):(\d+)', r'\1年\2月\3日 \4時\5分', search_date_time)
            speech_output = speech_output + search_date_time + '、に' + search_type
            if search_type == '始発' or search_type == '終電':
                speech_output = re.sub('00時.*$', 'の、' + search_type, speech_output)
            reprompt_text = GV_MSG_PROMPT_LAST
        speech_output = speech_output + 'です。'
    else:
        speech_output = speech_output + 'まだ設定されていません。' + GV_MSG_PROMPT1
        reprompt_text = GV_MSG_REPROMPT1

    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


def intent_LineNotify(intent, session):
    """インテント[LineNotify]
    ⑥検索した路線情報をLineに通知する
    """
    card_title = intent['name']
    should_end_session = False
    session_attributes = session['attributes'] if 'attributes' in session else {}

    # 路線情報を確認
    search_result = session_attributes.get('searchResult')
    url = session_attributes.get('url')
    if search_result is not None and url is not None:
        data = {'value1': search_result, 'value2': url}
        r = requests.post(GV_IFTTT_URL, data=data)
        if r.status_code == 200:
            speech_output = 'Lineに通知しました。'
            reprompt_text = GV_MSG_PROMPT_LAST
        else:
            speech_output = 'Lineへの通知に失敗しました。'
            reprompt_text = GV_MSG_ERROR_EXIT
            should_end_session = True
    else:
        speech_output = GV_MSG_PROMPT1
        reprompt_text = GV_MSG_REPROMPT1

    return build_response(session_attributes, build_speechlet_response(
        card_title, speech_output, reprompt_text, should_end_session))


# --------------- Events ------------------

def on_session_started(session_started_request, session):
    """ Called when the session starts """

    print('on_session_started requestId=' + session_started_request['requestId']
          + ', sessionId=' + session['sessionId'])


def on_launch(launch_request, session):
    """ Called when the user launches the skill without specifying what they
    want
    """

    print('on_launch requestId=' + launch_request['requestId'] +
          ', sessionId=' + session['sessionId'])
    # Dispatch to your skill's launch
    return get_welcome_response()


def on_intent(intent_request, session):
    """ Called when the user specifies an intent for this skill """

    print('on_intent requestId=' + intent_request['requestId'] +
          ', sessionId=' + session['sessionId'])

    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    # Dispatch to your skill's intent handlers
    if intent_name == 'SetStation':
        return intent_SetStation(intent, session)
    elif intent_name == 'SetDateTime':
        return intent_SetDateTime(intent, session)
    elif intent_name == 'AMAZON.NextIntent':
        return intent_NextPrevious(intent, session, 'next')
    elif intent_name == 'AMAZON.PreviousIntent':
        return intent_NextPrevious(intent, session, 'prev')
    elif intent_name == 'AMAZON.HelpIntent':
        return get_welcome_response()
    elif intent_name == 'AMAZON.CancelIntent' or intent_name == 'AMAZON.StopIntent':
        return handle_session_end_request()
    elif intent_name == 'AMAZON.RepeatIntent':
        return intent_Repeat(intent, session)
    elif intent_name == 'CheckCondition':
        return intent_CheckCondition(intent, session)
    elif intent_name == 'LineNotify':
        return intent_LineNotify(intent, session)
    else:
        # raise ValueError('Invalid intent')
        return handle_error_exit(session)


def on_session_ended(session_ended_request, session):
    """ Called when the user ends the session.

    Is not called when the skill returns should_end_session=true
    """
    print('on_session_ended requestId=' + session_ended_request['requestId'] +
          ', sessionId=' + session['sessionId'])
    # add cleanup logic here


# --------------- Main handler ------------------

def lambda_handler(event, context):
    """ Route the incoming request based on type (LaunchRequest, IntentRequest,
    etc.) The JSON body of the request is provided in the event parameter.
    """
    print('event.session.application.applicationId=' +
          event['session']['application']['applicationId'])

    """
    Uncomment this if statement and populate with your skill's application ID to
    prevent someone else from configuring a skill that sends requests to this
    function.
    """
    # if (event['session']['application']['applicationId'] !=
    #         'amzn1.echo-sdk-ams.app.[unique-value-here]'):
    #     raise ValueError('Invalid Application ID')

    if event['session']['new']:
        on_session_started({'requestId': event['request']['requestId']},
                           event['session'])

    if event['request']['type'] == 'LaunchRequest':
        return on_launch(event['request'], event['session'])
    elif event['request']['type'] == 'IntentRequest':
        return on_intent(event['request'], event['session'])
    elif event['request']['type'] == 'SessionEndedRequest':
        return on_session_ended(event['request'], event['session'])
