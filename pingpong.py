#  Ping-Pong
#  (c) 2017, Info-Logica Silverline s.r.l.
#           www.infologica.ro  
#  developed by Mihai Iliescu
#  Many thanks to:
#     http://www.nerdparadise.com/programming/pygame/part1


import pygame

pygame.init()
screen = pygame.display.set_mode((800, 600))
screen.fill((0, 0, 0))

speed = 60

clock = pygame.time.Clock()

class Square:
   sqCount = 0

   def __init__(self, x, y, c,  mx,  my):
      self.X = x
      self.Y = y
      self.Mx=mx
      self.My=my
      self.Color = c
      Square.sqCount += 1
   
   def paint(self,  s):
      pygame.draw.rect(s, self.Color, pygame.Rect(self.X, self.Y, 30, 30))

   def paintAt(self, s, x, y):
      self.X = x
      self.Y = y
      self.paint(s)
    
   def move(self):
     if ((self.X+30>800) or (self.X<0)): self.Mx=-self.Mx
     if ((self.Y+30>600) or (self.Y<0)): self.My=-self.My  
     self.X=self.X+self.Mx
     self.Y=self.Y+self.My

done = False

a = Square(100, 100, (255, 150, 50), 1, 0)
a.paint(screen)

b = Square(200, 100, (0, 250, 100), 0, 1)
b.paint(screen)

c = Square(300, 350,  (255, 150, 200), 1, 1)
c.paint(screen)

d = Square(700, 500,  (0, 100, 200), 1, 1)

x=400
y=300

wx=30
wy=30

p=1
q=1
sp=1
sq=1

n = Square(x, y, (210, 220, 250), 1, 1)

def rebound(i, j):
        i.X=i.X+i.Mx
        if crash(i, j):
            i.X=i.X-i.Mx
            i.My=-i.My
            j.My=-j.My
            i.X=i.X+i.Mx
            j.X=j.X+j.Mx
            i.Y=i.Y+i.My
            j.Y=j.Y+j.My
            print ("rebound Y")
        i.Y=i.Y+i.My
        if crash(i, j):
            i.Y=i.Y-i.My
            i.Mx=-i.Mx
            j.Mx=-j.Mx
            i.X=i.X+i.Mx
            j.X=j.X+j.Mx
            i.Y=i.Y+i.My
            j.Y=j.Y+j.My
            print ("rebound X")
    
def crash (i, j):
        col = False
        x=i.X
        y=i.Y
        c=j.X
        d=j.Y
        if (x>=c) and (x<=c+30) and (y>=d) and (y<=d+30): col = True
        if (x+wx>=c) and (x+wx<=c+30) and (y>=d) and (y<=d+30): col = True
        if (x>=c) and (x<=c+30) and (y+wy>=d) and (y+wy<=d+30): col = True
        if (x+wx>=c) and (x+wx<=c+30) and (y+wy>=d) and (y+wy<=d+30): col = True
        if col: 
            print "Crash!"
        return col



while not done:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            done = True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE:
                        n.Mx=0
                        n.My=0
                        n.Color=(240, 10, 50)
        if event.type == pygame.KEYDOWN and event.key == pygame.K_a:
                        if speed < 250: speed = speed +5
        if event.type == pygame.KEYDOWN and event.key == pygame.K_z:
                        if speed > 5: speed = speed - 5
                        print speed
    
    screen.fill((0, 0, 0))
 
    pressed = pygame.key.get_pressed()
    if pressed[pygame.K_UP]: n.My=-1
    if pressed[pygame.K_DOWN]: n.My =1
    if pressed[pygame.K_LEFT]: n.Mx = -1
    if pressed[pygame.K_RIGHT]: n.Mx = 1
   
    n.move()
    n.paint(screen)
    
    a.move()
    a.paint(screen)
    
    b.move()
    b.paint(screen)
    
    c.move()
    c.paint(screen)
    
    d.move()
    d.paint(screen)
    
    if crash(n, a):
        rebound(n, a)
    if crash(n, b):
        rebound(n, b)
    if crash(n, c):
        rebound(n, c)
    if crash(n, d):
        rebound(n, d)
        
    if crash(a, b):
        rebound(a, b)
    if crash(a, c):
        rebound(a, c)
    if crash(a, d):
        rebound(a, d)
    if crash(b, c):
        rebound(b, c)
    if crash(b, d):
        rebound(b, d)
    if crash(c, d):
        rebound(c, d)
        
    pygame.display.flip()
    clock.tick(speed)
