#! /usr/bin/python3
import sys
sys.path.append("..")

import random
from airmash.client import Client
from airmash.player import Player
from airmash.ships import ships
from airmash.types import ship_types
from airmash import packets
import threading
import time
import names
import math

UP = 'UP'
DOWN = 'DOWN'
LEFT = 'LEFT'
RIGHT = 'RIGHT'
FIRE = 'FIRE'
SPECIAL = 'SPECIAL'

ANGLE_FUZZ = math.pi / 15.
SHOOT_CUTOFF = 800.
FLEE_CUTOFF = 90.
MAX_TRIES=50
FPS = 60.

# This is a null player who can be used for debugging.
ZERO_PLAYER = Player(99999999)
ZERO_PLAYER.posX=0
ZERO_PLAYER.posX=0

def rare():
  return random.randrange(0, 10) == 0

typey=list(ship_types.keys())[random.randrange(0,5)]
if len(sys.argv) > 1:
  typey = sys.argv[1]
print("Type is ", typey)

name = names.get_first_name()
if len(sys.argv) > 2:
  name = " ".join(sys.argv[2:])
preferredTarget = name[4:]
if rare():
  name = "Robot " + name
name = name[:20]
print("Name is ", name)


me = None

def timeNear(x):
  return random.normalvariate(x, x/4.)

def get_nearest_player():
  #return ZERO_PLAYER
  minDist = float("inf")
  nearestPlayer = None
  for uid in client.players:
    p = client.players[uid]
    if p == client.player:
      continue
    if p.flag == client.player.flag:
      continue
    if preferredTarget in p.name:
      return p
    dist = p.dist_from(client.player)
    if (dist < minDist):
      minDist = dist
      nearestPlayer = p
  return nearestPlayer 

class StoppableThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self._event = threading.Event()

    def stop(self):
        self._event.set()

    def wait(self, timeout=1):
        return self._event.wait(timeout=timeout)

class ClientUpdate(StoppableThread):
    def __init__(self, *args, **kwargs):
        StoppableThread.__init__(self, *args, **kwargs)
    
    def target_player(self, player):
      startrot = client.player.rotation
      wrongness = client.player.angle_to(player) - client.player.rotation;
      going = None
      if (client.player.dist_from(player) > SHOOT_CUTOFF):
        going = UP
      if (client.player.dist_from(player) < FLEE_CUTOFF):
        going = DOWN 
      if going:
        self.send_keydown(going) 
      keypress = None
      if (wrongness < -ANGLE_FUZZ ):
        keypress = LEFT
      if wrongness > ANGLE_FUZZ:
        keypress = RIGHT
      if keypress is not None:
        self.send_keydown(keypress)
        turntime = wrongness/ships[ship_types[client.player.type]].turnFactor/FPS
        print("Turning for {} s to correct {} wrongness".format(turntime, wrongness))
        self.wait(abs(turntime))
        self.send_keyup(keypress)
        #self.wait(4)
        #print("{} is now the wrongness.".format(wrongness))
      if going:
        self.send_keyup(going)

    def charge_or_shoot(self, player):
      orig_health = client.player.health;
      dist = client.player.dist_from(player)
      cooldown = 0;
      rounds = 0 
      while client.player.dist_from(player) <= dist and rounds < 100:
        print ("My location: {0}, {1}".format(client.player.posX, client.player.posY))
        dist = client.player.dist_from(player)
        if (dist > SHOOT_CUTOFF) or cooldown > 0:
          keypress = (DOWN if rare() and rare() else UP)
          self.send_keydown(keypress)
          distTime = (dist / 2.) / ships[ship_types[client.player.type]].maxSpeed / FPS
          distTime = min(1, distTime)
          distTime = max(timeNear(distTime), .05)
          self.wait(distTime)
          self.send_keyup(keypress)
        else:
          keypress = FIRE
          # If neither prowler nor mohawk
          if not client.player.type in ['Mohawk', 'Prowler']:
            if (not (random.randrange(0, 3) == 0)) or (abs(client.player.angle_to(player)-client.player.rotation) > ANGLE_FUZZ * 3):
              keypress = SPECIAL
          #elif (abs(client.player.angle_to(player)-client.player.rotation) > ANGLE_FUZZ * 3):
            # Retarget.
          #  return
          if client.player.type == 'Predator':
            if rare():
              keypress = SPECIAL
          self.send_keydown(UP)
          if client.player.type == 'Mohawk':
            self.send_keyup(FIRE)
            self.wait(.2)
            self.send_keydown(FIRE)
          else:
            self.send_keydown(keypress)
            self.wait(.05)
            self.send_keyup(UP)
            self.wait(.05)
            cooldown = 3
            self.send_keyup(keypress)
        if (client.player.type == 'Prowler'):
          if (client.player.health < orig_health) or (cooldown == 1) or rare():
            self.send_keyup(SPECIAL)
            self.send_keydown(SPECIAL)
        cooldown-=1
        if (client.player.dist_from(get_nearest_player()) < dist/2.):
          # Someone is much closer. Abort, deal with the immediate threat.
          print("Punting to deal with near threat")
          return;
     
    def react_to_nearest(self):
      nearestPlayer = get_nearest_player()
      if (nearestPlayer is None):
        print("Nobody detected")
        return
      print("Aiming at {0} who is {1} away and {2} off".format(nearestPlayer.name,
                                                               nearestPlayer.dist_from(client.player),
                                                               client.player.angle_to(nearestPlayer)))
      print("Targetting {0}".format(nearestPlayer.name))
      # Attack them until someone dies or we're too badly shot at.
      # Are we pointed vaguely near them?
      self.target_player(nearestPlayer)
      # Attack.
      self.charge_or_shoot(nearestPlayer)
 
    def send_keydown(self, key):
      client.key(key=key, state=True)

    def send_keyup(self, key):
      client.key(key=key, state=False)

    def run(self):
        while not self.wait():
          if client.connected:
            break
        print("Players")
        for p in client.players:
          print("  ", client.players[p].name)
        packet = packets.build_player_command('COMMAND', com='respawn', data=str(ship_types[typey]))
        client.send(packet)
        if False: #rare(): 
          packet = packets.build_player_command('CHAT', text = "All hail the robot overlords!")
          client.send(packet)
        self.wait(2)
        if client.player.type == 'Mohawk':
          self.send_keydown("FIRE")
        while True:
            self.react_to_nearest()
            #my_status = client.players[me].status


client = Client()

@client.on('LOGIN')
def on_login(client, message):
    print("Client has logged in!")

_t_update = ClientUpdate()
_t_update.start()

client.connect(
    name=name,
    flag='HU',
    region='eu',
    room='ffa1',
)

_t_update.stop()
_t_update.join()

