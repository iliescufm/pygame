#!/usr/bin/env python
# -*- coding: latin-1 -*-

import pygame,os,sys
from pygame.locals import *
pygame.font.init()

global rouge,vert,bleu,noir,jaune,orange,blanc

RED=(255,0,0)
GREEN=(0,255,0)
BLUE=(0,0,255)
BLACK=(0,0,0)
YELLOW=(255,255,0)
ORANGE=(255,140,0)
WHITE=(255,255,255)
PINK=(255,0,255)
GREY=(128,128,128)

class AllItems(pygame.sprite.RenderUpdates):
    def __init__(self):
        pygame.sprite.RenderUpdates.__init__(self) 
        
class Scrolling (pygame.sprite.Sprite): 
        
    '''
    class Scrolling (pygame.sprite.Sprite): 
    def __init__(self,
    thanks = None,    # iterable of tuple as [(param1,param2,param3),
                                             (param1,param2,param3)]
                      with param1 for text to blit
                      with param2 = "c" to center
                                  = "l" to align right
                                  = "r" to align left
                      with param3 = size of the font
                      Example :            
                          [
                          ("Special Thanks to","c",32),
                          ("Guido van Rossum", "c",12),
                          ("For the invention of this awesome langage","c",22)
                          ]
    textcolor = None, # color RGB as (0,255,0)
    display = None,   # the display where blit as pygame.display.set_mode((640,480))
    background= None  # the path to the image as "./generic/bg2.png"
    ):

    Using it :
    Place Generic directory under your self directory project
    Add this at the beginning of your code : 
    from generic import generic
    Call like this :
    scroll=generic.Scrolling(
                            [("item1","c",12),
                            ("item2","l",24)
                            ],
                            None,
                            None,
                            None
                            )
    scroll.populate()
    '''
    def __init__(self,
                 thanks =None, # iterable of array of tuple as [("item1","c",12),("item2"],"c",24)]
                 textcolor = None, #color RGB as (0,255,0)
                 display = None, # the surface where blit
                 background= None # the path to the image as "./graph/img.png"
                ):

        print(self.__doc__)
        global fullname
        
        pygame.sprite.Sprite.__init__(self)
        self.clock = pygame.time.Clock()
        self.allitems=AllItems()
        
        # Initialyze attibutes
        
        if not thanks:
            self.thanks=[("Special Thanks to","c",22),
                         ("Guido van Rossum", "c",12),
                         ("For the invention of this awesome langage","c",12)
                        ]
        else:
            self.thanks=thanks
        if not textcolor:
            self.textcolor=GREEN
        else:
            self.textcolor=textcolor
            
        if not display: 
            self.surface = pygame.display.set_mode((320,240))
        else:
            self.surface = display
        
        if not background:
            self.background=(os.path.join(path,'bg.png'))
            print("bg",background)
        else:
            self.background=background
            
        self.bg=pygame.image.load(self.background).convert_alpha()
        self.bg=pygame.transform.scale(self.bg,(self.surface.get_rect().width,self.surface.get_rect().height))

        
    def populate(self):
        i=0
        lastsize=[]
        for tuple in self.thanks:
            # If not size passed
            try:
                self.font = pygame.font.Font(os.path.join(path,'Roboto-MediumItalic.ttf'),tuple[2])
            except:
                self.font = pygame.font.Font(os.path.join(path,'Roboto-MediumItalic.ttf'),12)
            # Surface of the font
            try:
                self.image=self.font.render(tuple[0].encode('latin-1'),1,self.textcolor)
            except:
                self.image=self.font.render(tuple[0],1,self.textcolor)
            # table of the size needed to blit exactly
            lastsize.append(self.image.get_rect().height)
            
            items=Font(self.image,self.surface,lastsize,i,tuple)
            self.allitems.add(items)
            i+=1
        choice=-1
        while len(self.allitems)>0 and choice!=0:
            self.clock.tick(20)
            for event in pygame.event.get():
                if event.type == pygame.KEYDOWN:
                    if event.key==97 or event.key==113 or event.key==pygame.K_ESCAPE:
                        choice=0
            self.surface.blit(self.bg,self.bg.get_rect())            
            self.allitems.update()
            self.allitems.draw(self.surface)
            pygame.display.update()

class Font(pygame.sprite.Sprite): 
    def __init__(self,surface,display,lastsize,index,tuple):
        
        pygame.sprite.Sprite.__init__(self)
        
        self.s=display
        self.image=surface
        self.rect=self.image.get_rect()
        
        # Position of the text
        y=0
        for e in range(index):
            y+=lastsize[e]
        #self.rect.top=self.s.get_rect().height/2 +y *
        self.rect.top=self.s.get_rect().bottom + y
        if tuple[1]=='c':
            self.rect.left=(self.s.get_rect().width-self.rect.width)/2
        elif tuple[1]=='l':
            self.rect.right=self.s.get_rect().width/2
        elif tuple[1]=='r':
            self.rect.left=self.s.get_rect().width/2
    
    def update(self):
        if self.rect.bottom>0:
            self.rect=self.rect.move(0,-1)
        else:
            self.kill()
            
if __name__ == '__main__':
    pygame.init()
    path='./'
    generic=Scrolling()
    generic.populate()
else:
    path='generic/'
        
        