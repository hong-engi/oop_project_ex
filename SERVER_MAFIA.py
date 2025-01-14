import socket
import threading
import time
import random

myip = '127.0.0.1'
myport = 50000
address = (myip, myport)

server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_sock.bind(address)
server_sock.listen()
print('마피아 서버 작동 시작')

client_list = []#접속한 플레이어들을 저장하는 곳
name_dic = {'example': '홍은기'}#플레이어들의 이름 저장
room_list = {}#방들을 저장하는 곳
room_player = {}#각 플레이어가 어느 방에 들어있는지 저장
min_player, max_player = 4, 12 # 최소, 최대 플레이어 수
mafia_num = {1: 0, 2: 1, 3: 1, 4: 1, 5: 1, 6: 2, 7: 2, 8: 3, 9: 3, 10: 3, 11: 3, 12: 3}#마피아 수
removed_name = []#나간 사람의 이름을 저장하는 곳(에러 방지를 위함)

#영어로 작성되었는지 검사하는 함수
def isalpha(text):
    for char in text:
        if not 'a' <= char <= 'z' and not 'A' <= char <= 'Z':
            return False
    return True

#CError - 서버 에러를 방지하기 위해 만든 클래스
class CError(BaseException):
    pass

#클라이언트를 삭제할 때 - 주로 연결이 잘못 끊겼을 때 쓰임
def remove(sock):
    try:
        global name_dic, client_list
        if not name_dic[sock] in removed_name:
            print('{}가 나갔습니다.'.format(name_dic[sock]))
            removed_name.append(name_dic[sock])
            if sock in room_player:
                room_player[sock].kick(sock)
            client_list.remove(sock)
            sock.close()
    except:
        return

#cerror_block - 거의 모든 함수에 데코레이터로 들어감 - 서버 오류가 났을 때 방지해주기 위함
def cerror_block(inner_func):
    def dec_f(*args, **kwargs):
        nonlocal inner_func
        try:
            return inner_func(*args, **kwargs)
        except:
            return

    return dec_f

#error_block - send와 recv함수를 데코레이트함 - 서버 오류가 났을 때 방지
#CError를 raise해줌으로써 cerror_block이 효과를 발휘하게 함
def error_block(inner_func):
    def dec_f(client, *args, **kwargs):
        nonlocal inner_func
        try:
            data = inner_func(client, *args, **kwargs)
        except:
            remove(client)
            raise CError
        if not data:
            remove(client)
            raise CError
        return data

    return dec_f

#메세지를 보내는 함수를 간략하게 사용하기 위함 - enter는 엔터 문자, line은 줄, line_chr은 줄에 쓰이는 문자를 바꿔준다.
#각 변수들의 default값은 다음과 같음, 즉 sendm(client,msg)를 실행하면 기본값으로 줄과 엔터 문자를 출력해준다.
def sendm(client, msg, enter=True, line=True, line_chr='='):
    if line:
        msg = line_chr * 100 + '\n' + msg
    if enter:
        msg = msg + '\n'
    error_block(socket.socket.send)(client, msg.encode('utf-8'))

#메세지를 받는 함수를 간략하게 사용하기 위함
def recvm(client):
    x = error_block(socket.socket.recv)(client, 1024)
    return x.decode('utf-8')

#Job클래스
class Job:
    def __init__(self, player, room):
        self.player = player # socket이 저장됨
        self.room = room # room클래스를 저장함으로써 room 안에 있는 변수들을 사용할 수 있게 함
        #alive,sel,name,shut_up : 각각 '살아 있음' '선택한 사람' '직업 이름' '성불 여부'를 판단함
        self.alive = True
        self.sel = None
        self.name = 'default'
        self.shut_up = False

    @cerror_block #데코레이터 - CError를 판단하여 해당 에러가 나면 remove함
    def night(self):
        self.sel = None
        self.room.print_players(self.player)#플레이어들의 이름과 번호 출력
        while not self.room.timeout:#타이머 - 타이머가 끝날 때까지 진행됨
            msg = recvm(self.player)#메시지를 받아, 이에 따른 게임을 진행함
            if self.room.timeout:
                break
            if msg == '!help':#도움말을 출력
                self.print_help()
                continue
            if msg[0] == '!':#첫 글자가 느낌표면, 선택함
                if self.name == '영매':
                    x = self.dead_select(msg)#죽은 사람 중에 선택
                else:
                    x = self.alive_select(msg)#산 사람 중에 선택
                if x is not False:
                    self.sel = self.select(self.room.p_list[x])#선택을 저장
                continue
            else:
                self.night_talk(msg)#밤에 말할 수 있는(예 : 마피아)는 night_talk 함수가 있어 서로 채팅이 가능함, 아니면 pass

    #night_talk를 상속 클래스들에서 따로 지정해줘야 사용 가능함
    def night_talk(self, msg):
        pass

    #낮 - 제한시간 전까지 서로 대화 가능함(살아있는 사람들끼리)
    @cerror_block
    def morning(self):
        while not self.room.timeout:
            msg = recvm(self.player)
            if self.room.timeout:
                return
            if msg == '!help':
                self.print_help()#도움말 출력
            else:
                self.room.talk(self.player, msg)#사람들끼리 대화하는 함수

    #투표 - 사람들마다 한 표씩 투표 가능
    @cerror_block
    def vote(self):
        vote_flag = False
        self.room.print_players(self.player)
        while not self.room.timeout:
            msg = recvm(self.player)
            if self.room.timeout:
                break
            if msg == '!help':
                self.print_help('morning')
            elif msg[0] == '!':#느낌표 - 사람 선택
                if not vote_flag:#이미 투표했다면, 걸러짐
                    x = self.alive_select(msg)
                    if x is False:
                        continue
                    else:#사람 선택
                        vote_flag = True
                        sel_player = self.room.p_list[x]
                        sendm(self.player, " - {}(을)를 선택하셨습니다.".format(name_dic[sel_player]))
                        broadcast(self.room.p_list, " - {}에 한 표!".format(name_dic[sel_player]),
                                  talker=[self.player])
                        if self.name == '정치인':#정치인은 두 표
                            sendm(self.player, "당신의 권력으로 두 표를 넣습니다.", line=False)
                            self.room.vote_list[x] += 2
                        else:#아니면 한 표
                            self.room.vote_list[x] += 1
                else:
                    sendm(self.player, "이미 투표하셨습니다.")
            else:#투표가 아니라면 채팅
                self.room.talk(self.player, msg)

    @cerror_block
    def print_help(self, mode='default'):#도움말 출력
        sendm(self.player, "사람을 선택할 때에는, 입력창에 '!(사람번호)' 를 입력하시면 됩니다.\n"
                           "예를 들어, {0}번 사람을 선택하고 싶으면 '!{0}'를 입력하시면 됩니다.".format(random.randint(1, 8)))

    @cerror_block
    def death(self):#죽음 - 죽은 사람들끼리 대화 가능, 게임이 끝날 때까지 상태 지속
        sendm(self.player, '축하해오! 당신은 뒤졌어오!')
        while not self.room.end_flag:
            msg = recvm(self.player)
            if self.room.end_flag:
                return
            send_msg = '[DEAD]{} : '.format(name_dic[self.player]) + msg
            if not self.shut_up:#성불될 시 채팅 X
                broadcast(self.room.dead_list, send_msg, talker=[self.player])
                #영매 존재 시 영매에게도 채팅 됨
                if self.room.shaman is not None and self.room.job[self.room.shaman].alive:
                    sendm(self.room.shaman, send_msg)
            else:
                sendm(self.player, "성불되어서 채팅을 사용할 수 없습니다. 닥치세요.")

    @cerror_block
    def alive_select(self, msg):#살아있는 사람 중에서 선택
        msg = msg[1:].strip(' ')
        if msg.isdigit() and 1 <= int(msg) <= self.room.player_num:
            if self.room.job[self.room.p_list[int(msg) - 1]].alive:
                return int(msg) - 1
            else:
                sendm(self.player, "사망한 플레이어는 선택할 수 없습니다.")
                return False
        else:
            sendm(self.player, "잘못된 입력입니다.")
            return False

    @cerror_block
    def dead_select(self, msg):#죽어있는 사람 중에서 선택
        msg = msg[1:].strip(' ')
        if msg.isdigit() and 1 <= int(msg) <= self.room.player_num:
            if not self.room.job[self.room.p_list[int(msg) - 1]].alive:
                return int(msg) - 1
            else:
                sendm(self.player, "살아 있는 플레이어는 선택할 수 없습니다.")
                return False
        else:
            sendm(self.player, "잘못된 입력입니다.")
            return False

    @cerror_block
    def final_words(self):#최후의 변론 - 투표에 걸린 사람이 마지막으로 말함
        if self.player == self.room.vote_select:
            while not self.room.timeout:
                msg = recvm(self.player)
                if self.room.timeout:
                    return
                broadcast(self.room.p_list, "< {} : {} >".format(name_dic[self.player], msg), talker=[self.player],
                          line=False)
        else:
            if self.room.timeout:
                return

    @cerror_block
    def final_vote(self):#투표에 걸린 사람을 찬반으로 죽일지 말지를 결정하는 투표
        final_vote_flag = False
        while not self.room.timeout:
            msg = recvm(self.player)
            if self.room.timeout:
                if self.name == '정치인':
                    self.room.downvote += 1
                self.room.downvote += 1
                return
            if not final_vote_flag:
                if msg == '찬성' or msg == 'Y' or msg == 'y':
                    if self.name == '정치인':
                        self.room.upvote += 1
                        self.room.downvote -= 1
                    self.room.upvote += 1
                    self.room.downvote -= 1
                    sendm(self.player, "찬성하셨습니다!")
                    final_vote_flag = True
                    continue
                if msg == '반대' or msg == 'N' or msg == 'n':
                    sendm(self.player, "반대하셨습니다!")
                    final_vote_flag = True
                    continue
            if msg[-17:] != 'fEEBgFFDASDL%%@FM':
                self.room.talk(self.player, msg)

    @cerror_block
    def select(self, player):#기본적으로는 밤에 선택을 하지 않음, 상속 클래스에서 세부적으로 선택
        sendm(self.player, "밤에 사람을 선택하는 직업이 아닙니다.")
        return None

#상속되는 클래스는 기본 형식은 Job 클래스와 같아 주석을 자세히 달지 않음
class Mafia(Job):
    def __init__(self, player, room):
        super().__init__(player, room)#상속받은 클래스의 init함수를 실행
        self.name = '마피아'#직업의 이름을 설정
        self.tutorial()#간단한 직업소개

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 마피아입니다.\n"
                           "밤에는 마피아끼리 상의하여 죽일 사람을 고르고,\n"
                           "낮에는 아무도 모르게 숨어 시민인 척 하세요.\n"
                           "마피아 수가 시민들보다 많을 시 승리합니다!")

    @cerror_block
    def night_talk(self, msg):#마피아는 밤에 채팅이 가능함
        broadcast(self.room.mafia_list, '[MAFIA]{} : {}'.format(name_dic[self.player], msg), talker=[self.player])
        broadcast(self.room.dead_list, '[MAFIA]{} : {}'.format(name_dic[self.player], msg), talker=[self.player])

    @cerror_block#직업에 따라 help 설명이 다름
    def print_help(self, mode='default'):
        super().print_help()
        sendm(self.player, "죽일 사람을 선택하세요!\n"
                           "마피아가 여러 명이어도 죽일 사람은 마지막에 선택된 한 사람만 죽일 수 있습니다.")

    @cerror_block
    def select(self, player):#마피아는 무제한으로 선택 가능, 또한 밤에 직업마다 선택에 따른 기능이 다르기 때문에 select함수는 직업마다 다름
        sendm(self.player, "{}(을)를 죽이기로 결정하셨습니다.".format(name_dic[player]))
        self.room.mafia_select = player
        broadcast(self.room.mafia_list, "[MAFIA_SELECT] {}님이 {}님을 선택하셨어요!"
                  .format(name_dic[self.player], name_dic[player]),
                  talker=[self.player])
        return [True, player]


class Police(Job):
    def __init__(self, player, room):
        super().__init__(player, room)
        self.name = '경찰'
        self.check_list = []
        self.use_skill = False
        self.tutorial()

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 경찰입니다.\n"
                           "밤에 사람을 선택하여 그 사람이 마피아인지 볼 수 있습니다.\n"
                           "마피아를 모두 처단할 시 승리합니다!")

    @cerror_block
    def select(self, player):
        if not self.use_skill:
            if player in self.check_list:
                sendm(self.player, "이미 조사한 사람입니다!")
            else:
                self.use_skill = True
                self.check_list.append(player)
                if self.room.job[player].name == '마피아':
                    sendm(self.player, "경크! {}(은)는 마피아입니다!!!".format(name_dic[player]))
                else:
                    sendm(self.player, "{}(은)는 마피아가 아니었습니다...".format(name_dic[player]))
                return [True, player]
        else:
            sendm(self.player, "이미 능력을 사용했습니다!")
        sendm(self.player, "지금까지의 조사결과를 보고싶으시다면 'watch'를 입력해주세요.")
        return None

    def night(self):
        self.use_skill = False
        super().night()

    @cerror_block
    def night_talk(self, msg):
        if msg == 'watch':
            if len(self.check_list) == 0:
                sendm(self.player, "조사를 진행하지 않았습니다!")
            else:
                self.check_print()

    @cerror_block
    def check_print(self):#경찰은 지금까지의 조사 결과를 볼 수 있음
        sendm(self.player, "-" * 100 + '\n' + "번호    이름")
        for player_num in range(len(self.room.p_list)):
            player = self.room.p_list[player_num]
            if player in self.check_list:
                sendm(self.player, "<{}>  -  [{}]".format(player_num + 1, name_dic[player]), line=False, enter=False
                      )
                if not self.room.job[self.room.p_list[player_num]].alive:
                    sendm(self.player, " - [DEAD]", line=False, enter=False)
                sendm(self.player, " - [{}]".format('마피아' if self.room.job[player].name == '마피아' else '시민'),
                      line=False)
        sendm(self.player, "-" * 100)

    @cerror_block
    def print_help(self, mode='default'):
        super().print_help()
        sendm(self.player, "조사할 사람을 선택하세요!\n"
                           "조사한 사람이 마피아인지 아닌지 확인이 가능합니다!")


class Reporter(Job):
    def __init__(self, player, room):
        super().__init__(player, room)
        self.name = '기자'
        self.report_skill = True#능력이 일회용이므로 따로 변수를 설정함
        self.tutorial()

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 기자입니다.\n"
                           "둘째 밤부터, 단 한 번 사람을 선택하여 그 사람의 직업을 볼 수 있습니다.\n"
                           "마피아가 모두 죽으면 승리합니다!")

    @cerror_block
    def select(self, player):
        if self.room.phase == 1:
            sendm(self.player, "첫 번째 밤에는 취재가 불가능합니다! ㅜㅜ")
            return None
        if self.report_skill:
            self.report_skill = False#능력 사용 시 다시는 사용하지 못함
            self.room.news = player
            sendm(self.player, "{}님을 취재하기로 결정하셨습니다!\n"
                               "다음 날에 살아있다면 기사를 낼 수 있을 겁니다! 살아 있다면요...".format(name_dic[player]))
            return [True, player]
        else:
            sendm(self.player, "이미 능력을 사용하셨습니다!")
        return None

    @cerror_block
    def print_help(self, mode='default'):
        super().print_help()
        sendm(self.player, "조사할 사람을 선택하세요!\n"
                           "조사한 사람의 직업이 낮에 밝혀집니다. 단, 마피아에게 죽으면 밝혀지지 않습니다ㅠㅜ")


class Sherlock(Job):
    def __init__(self, player, room):
        super().__init__(player, room)
        self.name = '탐정'
        self.use_skill = False
        self.tutorial()

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 탐정입니다.\n"
                           "밤에 사람을 선택하여 그 사람이 누굴 선택했는지를 볼 수 있습니다.\n"
                           "마피아가 모두 죽으면 승리합니다!")

    def night(self):
        self.use_skill = False#일회용 능력이 아니므로 밤마다 재충전됨
        super().night()#상속받은 클래스의 night함수를 실행

    @cerror_block
    def select(self, player):
        if player == self.player:
            sendm(self.player, "자신을 선택할 수 없습니다!")
            return None
        if not self.use_skill:
            self.use_skill = True
            sendm(self.player, "{}의 조사를 시작합니다!".format(name_dic[player]))
            inv = threading.Thread(target=self.investigate, args=(player,))
            inv.start()
            return [True, player]
        else:
            sendm(self.player, "이미 능력을 사용하셨습니다!")
        return None

    @cerror_block
    def investigate(self, player):
        p_job = self.room.job[player]
        while not self.room.timeout:
            if p_job.sel is not None and p_job.sel[0]:
                sendm(self.player, "[조사] {} - {}(을)를 선택하였음".format(name_dic[player], name_dic[p_job.sel[1]]),
                      line=False)
                p_job.sel[0] = False

    @cerror_block
    def print_help(self, mode='default'):
        super().print_help()
        sendm(self.player, "쫓아다닐 사람을 선택하세요\n"
                           "선택 후부터, 그 사람이 선택하는 사람을 모두 볼 수 있습니다.")


class Doctor(Job):
    def __init__(self, player, room):
        super().__init__(player, room)
        self.name = '의사'
        self.use_skill = False
        self.tutorial()

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 의사입니다.\n"
                           "밤에 사람을 선택하여 그 사람이 이번 밤에 마피아에게 죽는다면, 살려낼 수 있습니다.\n"
                           "마피아가 모두 죽으면 승리합니다!")

    def night(self):
        self.use_skill = False
        super().night()

    @cerror_block
    def select(self, player):
        sendm(self.player, "{}(을)를 치료합니다.".format(name_dic[player]))
        self.use_skill = True
        self.room.heal = player
        return [True, player]

    @cerror_block
    def print_help(self, mode='default'):
        super().print_help()
        sendm(self.player, "치료할 사람을 선택하세요!\n"
                           "치료하는 사람은 그 날 밤 마피아에게 선택을 당해도 살려낼 수 있습니다.")


class Politician(Job):
    def __init__(self, player, room):
        super().__init__(player, room)
        self.name = '정치인'
        self.tutorial()

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 정치인입니다. 당신이 하는 투표는 두 표로 적용됩니다.\n"
                           "투표로 죽지 않습니다!\n"
                           "마피아가 모두 죽으면 승리합니다!")

    @cerror_block
    def print_help(self, mode='default'):
        super().print_help()
        if mode == 'night':
            sendm(self.player, "정치인은 선택을 하지 않습니다.\n")
        if mode == 'morning':
            sendm(self.player, "투표에서 두 표를 낼 수 있습니다.\n"
                               "또한, 투표로 죽지 않습니다.")


class Soldier(Job):
    def __init__(self, player, room):
        super().__init__(player, room)
        self.name = '군인'
        self.armor = True
        self.tutorial()

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 군인입니다.\n"
                           "마피아의 공격을 한 번 막아냅니다!\n"
                           "마피아가 모두 죽으면 승리합니다!")

    @cerror_block
    def print_help(self, mode='default'):
        super().print_help()
        sendm(self.player, "군인은 선택을 하지 않습니다.\n", line=False)
        if self.armor:
            sendm(self.player, "방탄복을 입고 있어 마피아의 공격을 한 번 방어할 수 있습니다!")
        else:
            sendm(self.player, "방탄복이 부서졌습니다!")


class Terrorist(Job):
    def __init__(self, player, room):
        super().__init__(player, room)
        self.name = '테러리스트'
        self.use_skill = False
        self.tutorial()

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 테러리스트입니다.\n"
                           "밤에 사람을 하나 선택하여, 밤에 마피아에게 죽을 시 선택한 사람이 마피아라면 그 사람을 같이 데려갑니다!\n"
                           "투표에서 죽을 시, 아무나 선택하여 같이 저승길로 데려갈 수 있습니다!\n"
                           "마피아가 모두 죽으면 승리합니다!")

    def night(self):
        self.use_skill = False
        super().night()

    @cerror_block
    def select(self, player):
        if player == self.player:
            sendm(self.player, "자신을 선택할 수 없습니다!")
            return None
        sendm(self.player, "{0}(을)를 선택하셨습니다.".format(name_dic[player]))
        return [True, player]

    @cerror_block
    def print_help(self, mode='default'):
        super().print_help()
        if mode == 'night':
            sendm(self.player, "마피아로 의심되는 사람을 한 명 선택하세요!\n"
                               "만약 그 사람이 마피아이고, 마피아가 당신을 죽이면 그 사람을 같이 데려갈 수 있습니다!")
        if mode == 'morning':
            sendm(self.player, "당신은 테러리스트로써 마지막 역할을 하려고 합니다.\n"
                               "사람을 한 명 선택하세요. 그 사람은 당신의 마지막 여행과 함께할 것입니다.")

    @cerror_block
    def final_vote(self):
        if self.room.vote_select == self.player:
            self.room.downvote += 1
            sendm(self.player, "당신의 표는 반대표로 던져질 겁니다.\n"
                               "사람을 한 명 선택하세요. 같이 죽을 사람 하나를.\n"
                               "10초 드립니다. 선택은 신중하게.")
            self.room.print_players()
            sendm(self.player, "선택하는 방법? 번호만 입력하세요.")
            while not self.room.timeout:
                num = recvm(self.player)
                if self.room.timeout:
                    return
                if num.isdigit() and 1 <= int(num) <= self.room.player_num:
                    if self.room.job[self.room.p_list[int(num) - 1]].alive:
                        num = int(num) - 1
                    else:
                        sendm(self.player, "선택 대상이 아닙니다")
                        continue
                else:
                    sendm(self.player, "잘못 입력하셨습니다.")
                    continue
                self.sel = [True, self.room.p_list[num]]
        else:
            super().final_vote()


class Shaman(Job):
    def __init__(self, player, room):
        super().__init__(player, room)
        self.name = '영매'
        self.use_skill = False
        self.tutorial()

    @cerror_block
    def tutorial(self):
        sendm(self.player, "당신은 영매입니다.\n"
                           "당신은 죽은 사람과 대화가 가능합니다. 밤에는 죽은 사람들과 대화가 가능합니다.\n"
                           "밤에 사람을 하나 선택하여, 성불시킵니다. 성불을 하면 그 사람을 채팅 금지로 만들고 직업을 볼 수 있습니다.\n"
                           "마피아가 모두 죽으면 승리합니다!")

    def night(self):
        self.use_skill = False
        super().night()

    @cerror_block
    def select(self, player):
        if not self.use_skill:
            self.use_skill = True
            sendm(self.player, "{0}을 성불했습니다. {0}의 직업은 {1}입니다.".format(name_dic[player], self.room.job[player].name))
            broadcast([player], "성불당했습니다.")
            self.room.job[player].shut_up = True
            return [True, player]
        else:
            sendm(self.player, "오늘 밤에는 이미 너무 지쳤어요...")
            return None

    @cerror_block
    def night_talk(self, msg):
        broadcast(self.room.dead_list, '[영매]{} : '.format(name_dic[self.player]) + msg)

    @cerror_block
    def print_help(self, mode='default'):
        super().print_help()
        sendm(self.player, "죽은 사람의 채팅은 [DEAD]가 앞에 붙습니다.\n"
                           "사람을 하나 선택하여 성불시킬 수 있습니다."
                           "성불이 되면 영매에게 직업이 알려지고, 침묵 상태가 됩니다.")


@cerror_block
def name_select(sock):#이름 선택
    global name_dic
    name = '홍은기'
    while name in list(name_dic.values()):
        if name in list(name_dic.values()) and name != '홍은기':
            sendm(sock, "이미 있는 이름입니다. 다른 이름을 입력해주세요.\n이름 : ", enter=False)
        else:
            sendm(sock, "이름이 뭔가요?\n이름 : ", enter=False)
        name = recvm(sock).strip(' ')
        if name in removed_name:
            removed_name.remove(name)
            break
    name = name[0:9]
    sendm(sock, "안녕하세요, {}님!".format(name))
    client_list.append(sock)
    name_dic[sock] = name
    print("{}(이)가 접속하였습니다.".format(name_dic[sock]))


@cerror_block
def room_list_print(sock):#밤 이름 출력
    global room_list
    sendm(sock, "         [Room Lists]         \n" + "-" * 30)
    sendm(sock, "제목           사람 수", line=False)
    for name in room_list:
        room = room_list[name]
        sendm(sock, "{}{}    {} / {}".format(name, ' ' * (10 - len(name)), len(room.p_list), room.player_num),
              line=False)


@cerror_block
def connection():#클라이언트를 받는 함수
    global client_list

    while True:
        client_sock, client_addr = server_sock.accept()
        nameinput = threading.Thread(target=name_select, args=(client_sock,))
        nameinput.start()
        waiting = threading.Thread(target=wait, args=(client_sock, nameinput))
        waiting.start()


def broadcast(cast_list, msg, talker=[], enter=True, line=True, line_chr='='):#광역으로 메세지 보내줌
    #cast_list - 메세지를 받는 사람들
    #talker - 메세지를 받지 않는 사람들
    for sock in cast_list:
        if sock not in talker:
            try:
                sendm(sock, msg, enter=enter, line=line, line_chr=line_chr)
            except CError:
                remove(sock)
                continue


class Room:  # 방을 선언한 클래스
    def __init__(self, name, num):
        self.p_list = []
        self.job, self.mafia_list, self.dead_list = {}, [], []
        self.name = name
        self.player_num = num
        self.start_flag, self.end_flag = False, False
        self.timeout = False
        self.mafia_select, self.vote_select = None, None
        self.upvote, self.downvote = 0, 0
        self.vote_list = [0] * self.player_num
        self.heal = None
        self.shaman = None
        self.news = None
        self.phase = 0
        self.new_game()

    def new_game(self):#새로운 게임을 실행하는 함수
        game = threading.Thread(target=self.game_start)
        game.start()

    def talk(self, talker, msg):#채팅할 때 사용하는 함수
        broadcast(self.p_list, "{} : {}".format(name_dic[talker], msg), talker=[talker], line=False)

    @cerror_block
    def timer(self, sec):#시간을 재는 함수
        time.sleep(sec)
        self.timeout = True
        broadcast(self.p_list, "fEEBgFFDASDL%%@FM", line=False, enter=False, talker=self.dead_list)
        return

    @cerror_block
    def vote_result(self):#투표의 결과를 냄
        duo_flag, max_vote, voted_player = False, 0, 0
        for i in range(len(self.vote_list)):
            if self.vote_list[i] > max_vote:
                duo_flag, voted_player, max_vote = False, i, self.vote_list[i]
            elif self.vote_list[i] == max_vote:
                duo_flag = True
        if max_vote == 0:
            broadcast(self.p_list, "아무도 투표를 안 했나요? 처형자는 없습니다.")
            return
        elif duo_flag:
            broadcast(self.p_list, "투표를 가장 많이 받은 사람이 2명 이상이므로, 처형자는 없습니다.")
            return
        self.vote_select = self.p_list[voted_player]

    @cerror_block
    def final_vote_result(self):#찬반 투표의 결과를 냄
        if self.vote_select is not None:
            res = self.upvote >= self.downvote
            print("찬성 {0}, 반대 {1}".format(self.upvote, self.downvote))
            broadcast(self.p_list, "{}의 처형은 최종 투표에서 {}되었습니다!".format(name_dic[self.vote_select],'찬성' if res else '반대'))
            return res
        else:
            return False

    @cerror_block
    def people_add(self, sock):#해당 방 클래스에 사람을 접속시킴
        global name_dic
        if len(self.p_list) == self.player_num:
            sendm(sock, "인원이 꽉 찼습니다!")
            return False
        elif self.start_flag:
            sendm(sock, "이미 시작했습니다!")
            return False
        else:
            self.p_list.append(sock)
            self.job[sock] = Job(sock, room_list[self.name])
            room_player[sock] = self
            sendm(sock, "{} 방에 접속했습니다! ({}/{})".format(self.name, len(self.p_list), self.player_num))
            broadcast(self.p_list,
                      "{}님이 접속하셨습니다! ({}/{})".format(name_dic[sock], len(self.p_list), self.player_num),
                      talker=[sock])
            people_chat = threading.Thread(target=self.chat, args=(sock,))
            people_chat.start()
            return True

    def chat(self, sock):#방에 처음 들어왔을 때, 채팅에 들어가게 함.
        global name_dic
        try:
            sendm(sock, "채팅에 들어오셨습니당. 방을 나가시려면 '!나 나갈래!'라고 입력해주시면 됩니다.")
            while not self.start_flag:
                msg = recvm(sock)
                if self.start_flag:
                    return
                if msg == '!나 나갈래!' or msg is None:
                    self.kick(sock)
                    return
                broadcast(self.p_list, name_dic[sock] + ' : ' + msg, talker=[sock], line=False)
        except:
            self.kick(sock)
            return

    @cerror_block
    def kick(self, sock):#사람을 방에서 나가게 함
        if sock in self.p_list:
            try:
                sendm(sock, "방에서 나가졌습니다!")
            except:
                pass
            self.p_list.remove(sock)
            broadcast(self.p_list, "{}님이 나가셨습니다.".format(name_dic[sock]))
            if self.start_flag:
                broadcast(self.p_list, "한 명이 나갔기 때문에, 더 이상 진행할 수 없습니다.".format(name_dic[sock]))
                broadcast(self.p_list, "그럼 안녕히!")
                for player in reversed(self.p_list):
                    self.kick(player)
            if len(self.p_list) == 0:
                del room_list[self.name]
            waiting = threading.Thread(target=wait, args=(sock,))
            waiting.start()

    @cerror_block
    def game_start(self):#게임을 시작함
        while len(self.p_list) < self.player_num:#인원수가 채워질 때까지 기다림
            time.sleep(1)
        self.start_flag = 1
        broadcast(self.p_list, "@)!(확인", enter=False, line=False)
        broadcast(self.p_list, "인원수가 채워졌으니, 게임을 시작하겠습니다! 더 이상 나가실 수 없습니다.\n")
        time.sleep(5)
        for player in self.p_list:
            print(self.job[player].alive)
        cont = self.job_select()
        if not cont:
            self.new_game()
            return
        # 게임 시작
        self.phase = 1#낮밤 결정
        while self.game_ended() is False:
            self.daynnight()#진행하는 함수
            self.phase += 1
        #결과 출력
        self.end_flag = True
        #결과 출력
        broadcast(self.dead_list, "@)!(확인", enter=False, line=False)
        if self.game_ended() == 'C':
            broadcast(self.p_list, "마피아가 모두 죽었습니다.\n시민 팀이 승리했습니다!")
        if self.game_ended() == 'M':
            broadcast(self.p_list, "마피아가 시민보다 많습니다."
                                   "마피아 팀이 승리했습니다!")
        self.job_print()
        broadcast(self.p_list, "그럼 안녕히!")
        #게임이 끝난 후, 모두 나가게 함
        for player in reversed(self.p_list):
            self.kick(player)
        return

    @cerror_block
    def kill(self, player, killed):#플레이어를 죽게 하는 함수로, 사망 회피나 예외 상황 등을 모두 여기에 넣음
        if self.heal == player:
            broadcast(self.p_list, "{}(이)가 마피아의 공격을 받았지만, 의사의 치료를 받고 살았습니다!".format(name_dic[player]))
            return
        if killed == 'by terrorist':
            sendm(player, "테러리스트가 당신을 희생양으로 삼았습니다!", line_chr='!')
            broadcast(self.p_list, "{}(이)가 테러리스트와 같이 먼지가 되었습니다!.".format(name_dic[player]), talker=[player])
        if killed == 'by mafia':
            if self.job[player].name == '군인' and self.job[player].armor:  # 군인
                sendm(player, "마피아의 공격을 한 번 막아냈습니다! 방탄복이 부서져 이제는 방어할 수 없습니다.")
                broadcast(self.p_list, "{}(은)는 군인입니다. 마피아의 공격을 막아냈습니다!".format(name_dic[player]))
                self.job[player].armor = False
                return
            sendm(player, "마피아가 당신을 죽였습니다!", line_chr='!')
            broadcast(self.p_list, "{}(이)가 마피아의 공격을 받고 사망했습니다!".format(name_dic[player]), talker=[player])
        if killed == 'by vote':
            if self.job[player].name == '정치인':
                sendm(player, "당신은 정치인이므로 죽지 않습니다.")
                broadcast(self.p_list, "{}(은)는 정치인입니다. 투표로 죽지 않습니다.".format(name_dic[self.vote_select]),
                          talker=[player])
                return
            sendm(player, "민주주의의 법칙으로 인해 당신은 죽었습니다.", line_chr='!')
            broadcast(self.p_list, "{}(이)가 투표로 죽었습니다.".format(name_dic[player]), talker=[player])
        if self.job[player].name == '테러리스트':
            if self.job[player].sel is not None:
                selected_player = self.job[player].sel[1]
                if self.job[selected_player].name == '마피아':
                    self.kill(self.job[player].sel[1], 'by terrorist')
            self.job[player].sel = None
        if self.job[player].name == '기자':
            self.news = None
        self.job[player].alive = False
        self.dead_list.append(player)
        dead_chat = threading.Thread(target=self.job[player].death, args=())
        dead_chat.start()

    @cerror_block
    def job_print(self):#직업을 출력해준다.
        text = "-" * 30 + '\n' + "이름             직업" + '\n'
        for player in self.p_list:
            name = name_dic[player]
            text += "{}{}    {} {}\n".format(name, ' ' * (10 - len(name)), self.job[player].name,
                                             '[생존]' if self.job[player].alive else '[사망]')
        broadcast(self.p_list, text, line=False)

    @cerror_block
    def news_print(self):#기자의 기사를 출력해준다.
        if self.news is not None:
            broadcast(self.p_list,
                      "!!!!속보에요 속보!!!!\n{}(이)가 {}래요!\n".format(name_dic[self.news],
                                                               self.job[self.news].name) + "#" * 100,
                      line_chr='#')
            self.news = None

    @cerror_block
    def daynnight(self):#낮과 밤을 모두 처리하는 함수
        day_num = self.phase // 2
        if self.phase == 1:#맨 처음 밤, 튜토리얼을 출력해줌
            for player in self.p_list:
                self.job[player].print_help('night')
                sendm(player, '다음에도 도움이 필요하다면 "!help"를 입력해주세요.')
        if self.phase % 2 == 1:#밤을 진행
            broadcast(self.p_list, "{}번째 밤".format(day_num))
            self.happening('night', 25)#밤
            if self.mafia_select is not None:
                self.kill(self.mafia_select, 'by mafia')
            else:
                broadcast(self.p_list, "오늘 밤은 조용하네요...")
            self.mafia_select, self.heal = None, None
        else:#낮을 진행
            broadcast(self.p_list, "{}번째 낮".format(day_num))
            self.news_print()
            morning_time = 8 * (self.player_num - len(self.dead_list))
            self.happening('morning', 30 if 30 <= morning_time else morning_time)#낮
            broadcast(self.p_list, '투표 시간입니다! 투표할 사람을 선택해주세요. \n'
                                   '선택하는 방법은 "!(선택 번호)"를 입력해주시면 됩니다.')
            self.happening('vote', 15)#투표
            self.vote_result()
            voted_player = self.vote_select
            if voted_player is not None:
                broadcast(self.p_list, "{}의 최후의 한 마디가 있겠습니다!".format(name_dic[self.vote_select]))
                self.happening('final_words', 15)#최후의 변론
                broadcast(self.p_list, "찬반 투표 시간입니다!\n"
                                       "{}(을)를 죽이는 데 찬성하시면 '찬성' 또는 'y',\n"
                                       "반대하시면 '반대' 또는 'n'을 입력하세요.\n"
                                       "입력하지 않으면 반대표로 투표됩니다.".format(name_dic[self.vote_select])
                          )
                self.happening('final_vote', 10)#찬반 투표
            if self.final_vote_result():
                self.kill(voted_player, 'by vote')
            self.vote_init()

    def vote_init(self):#투표 후 투표 변수 초기화
        self.upvote, self.downvote, self.vote_list = 0, 0, [0] * self.player_num
        self.vote_select = None

    @cerror_block
    def happening(self, func_name, timer_time):#Job 클래스 안에 있는 'func_name'이라는 이름을 가진 함수를 모든 플레이어들에 대해
        #일괄적으로 실행함, timer_time만큼 타이머를 잼
        thread_list = []
        self.timeout = False
        timewatch = threading.Thread(target=self.timer, args=(timer_time,))
        timewatch.start()
        broadcast(self.p_list, "시간 제한은 {}초입니다.".format(timer_time), line=False)
        for player in self.job:
            if self.job[player].alive:
                thread = threading.Thread(target=getattr(self.job[player], func_name), args=())
                thread_list.append(thread)
                thread.start()
        for thread in thread_list:
            thread.join()

    def game_ended(self):#게임이 끝났는지 판별하는 함수
        mafia_n, citizen_n = 0, 0
        for player in self.p_list:
            if player not in self.dead_list:
                if self.job[player].name == '마피아':
                    mafia_n += 1
                else:
                    if self.job[player].name == '정치인':
                        citizen_n += 2
                    else:
                        citizen_n += 1
        if mafia_n == 0:
            return 'C'#시민 승
        if mafia_n >= citizen_n:
            return 'M'#마피아 승
        return False

    @cerror_block
    def print_players(self, sock):#플레이어들의 정보를 출력
        sendm(sock, "*" * 100 + '\n' + "번호     이름")
        for player_num in range(len(self.p_list)):
            msg = "<{}>  -  [{}]".format(player_num + 1, name_dic[self.p_list[player_num]])
            if not self.job[self.p_list[player_num]].alive:
                msg += " [DEAD]"
            sendm(sock, msg, line=False)
        sendm(sock, "*" * 100, line=False)

    @cerror_block
    def job_select(self):#게임 시작 때 직업을 무작위로 지정하는 함수
        try:
            job_name_list = [Shaman, Terrorist, Soldier, Sherlock, Reporter, Politician]
            job_num_dic = {Mafia: mafia_num[self.player_num], Police: 1, Doctor: 1}
            cnt = job_num_dic[Mafia] + 2
            random.shuffle(job_name_list)
            for job_class in job_name_list:
                if cnt >= self.player_num:
                    break
                job_num_dic[job_class] = 1
                cnt += 1
            job_index = 0
            for player in self.p_list:
                x = random.choice(list(job_num_dic.keys()))
                while job_num_dic[x] == 0:
                    x = random.choice(list(job_num_dic.keys()))
                self.job[player] = x(player, room_list[self.name])
                if self.job[player].name == '마피아':
                    self.mafia_list.append(player)
                if self.job[player].name == '영매':
                    self.shaman = player
                job_num_dic[x] -= 1
                job_index += 1
            for player in self.job:
                print('{}:{}'.format(name_dic[player], self.job[player].name))
            return True
        except Exception as e:
            print(e)
            broadcast(self.p_list, "오류가 났네요...? 5초만 기다리죠.")
            time.sleep(5)
            return False


@cerror_block
def wait(sock, name_f=None):#맨 처음 접속했을 때 기다리는 함수
    global name_dic, min_player, max_player, room_list
    if name_f is not None:
        name_f.join()
    while True:
        sendm(sock, "방을 만드시려면 'new room'을, 지금 있는 방에 들어가시려면 'enter room'을 입력해주세요.\n입력 : ", enter=False)
        msg = recvm(sock)
        if msg is None:
            return
        if msg == 'new room':#새 방 만들기
            room_name, room_maxp = None, None
            sendm(sock, "방의 이름을 입력해주세요. (영어만 가능)\n방 이름 : ", enter=False)
            while room_name is None or not isalpha(room_name) or room_name in room_list:
                if room_name in room_list:
                    sendm(sock, "이미 있는 방 이름입니다.\n방 이름 : ", enter=False)
                elif room_name is not None:
                    sendm(sock, "영어만 가능합니다.\n방 이름 : ", enter=False)
                room_name = recvm(sock)[0:9]
            sendm(sock, "입력되었습니다.")
            sendm(sock, "인원은 몇 명으로 할까요? {}~{}명 사이에서 입력해주세요.\n인원수 : ".format(min_player, max_player), enter=False)
            while room_maxp is None or not room_maxp.isdigit() or int(room_maxp) < min_player or int(
                    room_maxp) > max_player:
                if room_maxp is not None:
                    sendm(sock, "{}~{}명 사이에서 입력해주세요.\n인원수 : ".format(min_player, max_player), enter=False)
                room_maxp = recvm(sock)
            room_maxp = int(room_maxp)
            sendm(sock, "입력되었습니다.")
            room_list[room_name] = Room(room_name, room_maxp)
            sendm(sock, "{}({}명 방)이 생성되었습니다.".format(room_name, room_maxp))
            room_list[room_name].people_add(sock)
            return

        if msg == 'enter room':#방 들어가기
            if len(room_list) == 0:
                sendm(sock, "만들어져 있는 방이 없네요. 새로운 방을 만들어주세요!")
                continue
            else:
                added_flag = False
                back_flag = False
                while not added_flag:
                    room_list_print(sock)
                    sendm(sock, "들어가고 싶은 방의 이름을 입력해주세요.\n뒤로 가려면 '!뒤로!'라고 입력해주세요.\n방 이름 : ", enter=False)
                    room_name = None
                    while room_name not in room_list:
                        if room_name == '!뒤로!':
                            back_flag = True
                            break
                        if room_name is not None:
                            sendm(sock, "해당 이름을 가진 방이 없습니다.\n방 이름 : ", enter=False)
                        room_name = recvm(sock)
                    if back_flag:
                        break
                    sendm(sock, "보내드릴게요.")
                    added_flag = room_list[room_name].people_add(sock)
                    if not added_flag:
                        continue
                if back_flag:
                    continue
                return


Base_Server = threading.Thread(target=connection, args=())#클라이언트의 연결을 기다리는 스레드 실행
Base_Server.start()

Base_Server.join()
server_sock.close()
