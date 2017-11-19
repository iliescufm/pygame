#!/usr/bin/env python
# -*- coding: utf-8 -*-

################################################################################
# 
# PYTHON > 2.6 |  WINDOWS TESTED |  LINUX TESTED 
# Auteur du présent code : Deregnaucourt Maxime  space.max@free.fr   
#                                                                     
#                                                                             
# Thank a lot to :                           
# Maya et Gabriel pour leur talent artistique
# Pygame's team
# http://www.universal-soundbank.com/ for the sounds
# http://www.1001freefonts.com/retro-fonts.php for the fonts
# Josmiley for all tools and modules
#                
#
# HELP KEY USED
# LEFT, RIGHT, SPACE FOR SHOOT, B FOR BOMBE, P FOR PAUSE
# Q FOR QUIT MENU / ECHAP FOR QUIT THE GAME
################################################################################

import pygame,sys,random,os,datetime,math
from pygame.locals import *
from platform import system
from slidemenu import slidemenu
from generic import generic
from include import mycolors
from include import words
OS = system().upper()
random.seed()
#_______________________________________________________________________________
# Variables globales /  global variables

FPS=50
MODE=0
LANG=0 # 0 french 1 English

#_______________________________________________________________________________
class AllMunition(pygame.sprite.RenderUpdates):
	def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________________________________________________________________
class AllMunition2(pygame.sprite.RenderUpdates):
	def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________________________________________________________________
class AllGun(pygame.sprite.RenderUpdates):

	 def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________________________________________________________________
class AllAlien(pygame.sprite.RenderUpdates):

	 def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________________________________________________________________
class AllExtra(pygame.sprite.RenderUpdates):

	 def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________ ________________________________________________________
class AllCadeau(pygame.sprite.RenderUpdates):
	def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________________________________________________________________
class AllBombeAlien(pygame.sprite.RenderUpdates):
	def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________________________________________________________________
class AllBoss(pygame.sprite.RenderUpdates):

	 def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________________________________________________________________
class AllPolygon(pygame.sprite.RenderUpdates):

	 def __init__(self):
		pygame.sprite.RenderUpdates.__init__(self)
#_______________________________________________________________________________
		
class Jeu():

	def __init__(self,width=640,height=480):

		pygame.init()

		# Les dimensions de la surface
		# the dimensions of the Surface of the game

		self.width=width
		self.height=height
		self.size = width, height
		self.mode=0 # use to toggle fullscreen
		self.ecran()

		pygame.mixer.set_num_channels(30)

		########################################################################
		# Les sons / The sounds
		########################################################################

		self.sound_alien_cry=pygame.mixer.Sound("./sound/sprite.ogg")
		self.sound_alien_attack=pygame.mixer.Sound("./sound/alert_attack.ogg")
		self.sound_alien_expl=pygame.mixer.Sound("./sound/explode.ogg")
		self.sound_boss_affected=pygame.mixer.Sound("./sound/expl1.ogg")
		self.sound_boss_cry=pygame.mixer.Sound("./sound/boss_cry.ogg")
		self.sound_vie=pygame.mixer.Sound("./sound/vie.ogg")
		self.sound_bombe=pygame.mixer.Sound("./sound/bombe.ogg")
		self.sound_power=pygame.mixer.Sound("./sound/shot2.ogg")
		self.sound_shield=pygame.mixer.Sound("./sound/shield.ogg")
		self.sound_alert=pygame.mixer.Sound("./sound/alert.ogg")
		self.sound_vaisseau_expl=pygame.mixer.Sound("./sound/select_choose.ogg")
		self.sound_extra_life=pygame.mixer.Sound("./sound/extralife.ogg")

		########################################################################
		# The images
		########################################################################

		# Le tableau des chemins d'images PNG sur 13 niveaux, 5 images par sprites
		# Arrray of the paths of the images for the aliens sprite / 5 images per alien sprite

		self.png=14*[5*[""]]

		self.png[0]=["./graph/space11.png","./graph/space12.png","./graph/space13.png","./graph/space14.png","./graph/space15.png"]
		self.png[1]=["./graph/space21.png","./graph/space22.png","./graph/space23.png","./graph/space24.png","./graph/space25.png"]
		self.png[2]=["./graph/space31.png","./graph/space32.png","./graph/space33.png","./graph/space34.png","./graph/space35.png"]
		self.png[3]=["./graph/space81.png","./graph/space82.png","./graph/space83.png","./graph/space84.png","./graph/space85.png"]
		self.png[4]=["./graph/space71.png","./graph/space72.png","./graph/space73.png","./graph/space74.png","./graph/space75.png"]
		self.png[5]=["./graph/space61.png","./graph/space62.png","./graph/space63.png","./graph/space64.png","./graph/space65.png"]
		self.png[6]=["./graph/space51.png","./graph/space52.png","./graph/space53.png","./graph/space54.png","./graph/space55.png"]
		self.png[7]=["./graph/space91.png","./graph/space92.png","./graph/space93.png","./graph/space94.png","./graph/space95.png"]
		self.png[8]=["./graph/space41.png","./graph/space42.png","./graph/space43.png","./graph/space44.png","./graph/space45.png"]
		self.png[9]=["./graph/space10.1.png","./graph/space10.2.png","./graph/space10.3.png","./graph/space10.4.png","./graph/space10.5.png"]
		self.png[10]=["./graph/space11.1.png","./graph/space11.2.png","./graph/space11.3.png","./graph/space11.4.png","./graph/space11.5.png"]
		self.png[11]=["./graph/space12.1.png","./graph/space12.2.png","./graph/space12.3.png","./graph/space12.4.png","./graph/space12.5.png"]
		self.png[12]=["./graph/space13.1.png","./graph/space13.2.png","./graph/space13.3.png","./graph/space13.4.png","./graph/space13.5.png"]
		
		# here are the extras aliens
		self.png[13]=["./graph/space14.1.png","./graph/space14.2.png","./graph/space14.3.png","./graph/space14.4.png","./graph/space14.5.png"]

		# Le tableau des images PNG 13 niveaux, 5 images par sprites
		# Arrray of images (surface) for the aliens sprite / 5 images per alien sprite

		self.png2=[]

		# Load the images of the aliens
		i=0
		while i<len(self.png):
			self.pngs=5*[pygame.Surface]
			for j in range(5):
				self.pngs[j]=pygame.image.load(self.png[i][j]).convert_alpha()
			self.png2.append(self.pngs)
			i+=1

		# Array of images for the explosion of the aliens
		self.alien_explosion=[pygame.Surface] * 5
		i=1
		while i<6:
			chemin="./graph/alien_expl" + str(i) + ".png"
			#  Load images of aliens's explosions
			self.alien_explosion[i-1]=pygame.image.load(chemin).convert_alpha()
			i+=1

		# Load the Munitions of the ship

		self.munition01=pygame.image.load("./graph/munition01.png").convert_alpha()
		self.munition02=pygame.image.load("./graph/munition02.png").convert_alpha()
		self.munition03=pygame.image.load("./graph/munition03.png").convert_alpha()
		self.munition04=pygame.image.load("./graph/munition04.png").convert_alpha()
		self.munition05=pygame.image.load("./graph/munition05.png").convert_alpha()
		self.munition06=pygame.image.load("./graph/munition06.png").convert_alpha()

		# Load the bombs of the aliens

		self.alien_bomb10=pygame.image.load("./graph/munition10.png").convert_alpha()
		self.alien_bomb20=pygame.image.load("./graph/munition20.png").convert_alpha()
		self.alien_bomb30=pygame.image.load("./graph/munition30.png").convert_alpha()
		self.alien_bomb40=pygame.image.load("./graph/munition40.png").convert_alpha()
		self.alien_bomb50=pygame.image.load("./graph/munition50.png").convert_alpha()

		# Load Boss's image
		self.boss=[pygame.Surface] * 5
		self.boss[0]=pygame.image.load("./graph/boss01.png").convert_alpha()
		self.boss[1]=pygame.image.load("./graph/boss02.png").convert_alpha()
		self.boss[2]=pygame.image.load("./graph/boss03.png").convert_alpha()
		self.boss[3]=pygame.image.load("./graph/boss04.png").convert_alpha()


		# Charge les images du vaisseau
		# Load the images for the ship. To do : use an array

		self.vaisseau01=pygame.image.load("./graph/vaisseau01.png").convert_alpha()
		self.vaisseau02=pygame.image.load("./graph/vaisseau02.png").convert_alpha()
		self.vaisseau03=pygame.image.load("./graph/vaisseau03.png").convert_alpha()
		self.vaisseau04=pygame.image.load("./graph/vaisseau04.png").convert_alpha()
		self.vaisseau05=pygame.image.load("./graph/vaisseau05.png").convert_alpha()
		self.vaisseau06=pygame.image.load("./graph/vaisseau06.png").convert_alpha()
		self.vaisseau07=pygame.image.load("./graph/leftgun.png").convert_alpha()
		self.vaisseau08=pygame.image.load("./graph/rightgun.png").convert_alpha()
		self.vaisseau09=pygame.image.load("./graph/vaisseau09.png").convert_alpha()
		
		# Load the images of the explosion of the ship

		self.vaisseau_explosion=[pygame.Surface] * 12
		i=1
		while i<13:
			chemin="./graph/vaisseau-expl" + str(i) + ".png"
			self.vaisseau_explosion[i-1]=pygame.image.load(chemin).convert_alpha()
			i+=1

		# Tableau des images pour chaque piege
		# Array of the images of the trap (tnt) used for the explosion

		self.piege_expl=[pygame.Surface] * 7
		i=1
		while i<8:
			chemin="./graph/piege_expl" + str(i) + ".png"
			self.piege_expl[i-1]=pygame.image.load(chemin).convert_alpha()
			i+=1

		# Nepomuk is big !
		self.nepomuk_img=pygame.image.load("./graph/nepomuk.png").convert_alpha()

		# Background for speed menu
		self.bg=pygame.image.load("./graph/fond.png").convert_alpha()
		self.bgRect=self.bg.get_rect()

		# Background for menu
		self.bg2=pygame.image.load("./graph/fond2.png").convert_alpha()
		self.bgRect2=self.bg2.get_rect()

		# Background for scrolling
		self.bgscroll=pygame.image.load("./graph/scroll.png").convert_alpha()
		self.optionScroll=0
		
		# Various

		self.cadeau=pygame.image.load("./graph/cadeau.png").convert_alpha()
		self.bombe=pygame.image.load("./graph/bombe.png").convert_alpha()
		self.power=pygame.image.load("./graph/power.png").convert_alpha()
		self.piege=pygame.image.load("./graph/piege.png").convert_alpha()
		self.shield=pygame.image.load("./graph/shield.png").convert_alpha()
		self.bombe_boss01=pygame.image.load("./graph/bombe_boss01.png").convert_alpha()
		self.bombe_boss02=pygame.image.load("./graph/bombe_boss02.png").convert_alpha()
		self.invinsibility=pygame.image.load("./graph/vaisseau09.png").convert_alpha()

		self.choixMenu=pygame.image.load("./graph/maya2.png").convert_alpha()
		self.choixMenuRect=self.choixMenu.get_rect()
		self.choixMenuRect=self.choixMenuRect.move(460,258)

		# Le groupe d'alien du jeu
		# group's alien UFO
		self.allalien=AllAlien()

		# Le groupe d'alien extra du jeu
		# group's alien UFO
		self.allextra=AllExtra()

		# Le groupe des tirs Aliens
		# group's bombs for alien UFO
		self.allbombealien=AllBombeAlien()

		# Le groupe des tirs du vaisseau
		# group's bombs for space ship
		self.allmunition=AllMunition()
		self.allmunition2=AllMunition2()

		# Le groupe des cadeaux
		# group's surprises

		self.allcadeau=AllCadeau()
		
		# Group of guns
		self.allgun=AllGun()
	
		# Group of Boss
		self.allboss=AllBoss()
	
		# Group of Polygon
		self.allpolygon=AllPolygon()
	
		# Le tableau des highscores
		# Array of highscore

		self.highscore=[]

		self.vie=3 # Life ICI
		self.niveau=1 # Level

		self.score=0
		self.extra_bombe=0 # ICI
		self.nb_extra_bombe=0
		self.extra_bombe_value=0
		self.extra_life=0

		# Horloge pour les tirs Aliens / Clock for the Alien's shoots
		self.clock=pygame.time.Clock()

		# Horloge pour les boucliers Aliens / Clock for the Alien's shields
		self.clock_shield=pygame.time.Clock()
		
		# Clock for bigpower
		self.clockpower=pygame.time.Clock()
		self.timepower=0

		self.highscore_load()

		pygame.mouse.set_visible(False)
		
	def ecran(self,couleur=(0,0,0,)):

		# Définition l'écran
		# Definition of the main surface

		self.couleur=couleur
		self.surface= pygame.display.set_mode(self.size,MODE)
		pygame.display.set_caption('Space Max')

	def play_sound(self,sound,loop=0):
		
		try:
			canal=pygame.mixer.find_channel(force=True)
			canal.stop()
			canal.play(sound,loop)
		except:
			sound.play(loop)
			pass
	
	def toogle(self):
		
		global MODE
		# bascule entre mode fenêtré et plein écran
		# switch display between windowed and full screen

		if MODE==0:
			MODE=FULLSCREEN
		else:
			MODE=0
		s=self.surface.copy()
		self.surface= pygame.display.set_mode(self.size,MODE)
		self.surface.blit(s,s.get_rect())
		pygame.display.update()

	########################################################################
	# Ajoute les Aliens au jeu
	# Add ufo sprite
	########################################################################

	def ajoute_alien(self,nb_alien=0,nb_alien_max=15):
		self.nb_alien=nb_alien
		self.nb_alien_max=nb_alien_max
		if self.nb_alien<self.nb_alien_max:
			self.nb_alien+=1
		else:
			self.nb_alien=1
			
		# list of coordinates for abscissa
		valy=[44,64,96,128,160]
		valx=[]
		i=0
		# Fills the ordinates by step of 32 pixels
		while i<=480:
			valx.append(int(i))
			i+=32
		i=0
		while i<self.nb_alien:

			# Choisit les coordonnées de l'alien
			# Choose coodonnates

			y=random.sample(valy,1)
			x=random.sample(valx,1)
			# Création de l'objet avec passage des coordonnées de départ
			# Create an alien
			objet_alien=Alien(x[0],y[0])
			
			# Evite d'utiliser les mêmes coordonnées / Avoid to use the same coordinates
			valx.remove(x[0])
			i+=1

	def update(self,zone):
		# update a zone of main surface
		self.zone=zone
		pygame.display.update(self.zone)

	def tick_power(self):
		self.clockpower.tick(FPS)
		self.timepower+=self.clockpower.get_time()

		# Each minute you can take your chance with Nepomuk
		if self.timepower>30000:
		   self.timepower=0
		   if jeu.nb_alien>5:
			   self.nepomuk=Nepomuk()

	def raz(self):
		self.surface.fill(mycolors.BLACK)

	def empty(self):

		# Erase all sprites We never know !!!
		
		# Erase all fire of the ship
		self.allmunition.empty()
		
		# Effacement tir des Aliens
		# Erase all the bomb of the aliens
		self.allbombealien.empty()
		
		# Effacement des Aliens
		# Erase all the aliens
		self.allalien.empty()
		
		# Stop the sounds
		pygame.mixer.stop()
		
		self.nb_extra_bombe=0

	def pause(self):
		pause=0
		pygame.event.clear(KEYDOWN)
		e=pygame.event.Event(KEYDOWN,key=K_n)
		while pause!=1:
			for e in pygame.event.get():
				if e.type == pygame.KEYDOWN:
					if e.key==112:
						pause=1
					elif e.key==97 or e.key==113 or e.key==27:
						self.break_high=True
						pause=1
			pygame.time.wait(100)

	########################################################################
	#   The HighScore
	########################################################################

	def highscore_load(self):

		self.fichier_score=True
		try:
			fic=open("./high.txt","r")
		except:
			print ("Erreur ouverture hight.txt")
			self.fichier_score=False
		if self.fichier_score==True:
			eof=False
			while eof!=True:
				ligne=fic.readline()
				ligne=ligne[0:-1]
				if ligne=="":
					eof=True
				else:
					self.highscore.append([int(ligne.split(",")[0]),str(ligne.split(",")[1])])
			self.highscore.sort(reverse=True)
		else:
			 self.highscore.append([0,"Space Max"])

	def highscore_write(self):
		try:
			if self.fichier_score==True:
			   fic=open("./high.txt","a")
			else:
			   fic=open("./high.txt","w")
			self.raz()
			font=pygame.font.Font(None,24)

			text1 = font.render(words.words[14][LANG],1,mycolors.GREEN,mycolors.BLACK)
			text1Rect=text1.get_rect()
			text1Rect=text1Rect.move(int((self.width-text1Rect.width)/2),100)
			self.surface.blit(text1,text1Rect)
			self.update(text1Rect)

			nom=""
			flag=True
			while flag==True:
				for e in pygame.event.get():
					if e.type==KEYDOWN:

						### A-Z only
						if e.key>=97 and e.key<=122:
							if len(nom)<8:
								s=pygame.key.name(e.key)
								nom+=s
								text2 = font.render(nom,1,mycolors.GREEN,mycolors.RED)
								text2Rect=text2.get_rect()
								text2Rect=text2Rect.move(text1Rect.right,100)
								self.surface.blit(self.bg,text2Rect,text2Rect)
								self.update(text2Rect)
								self.surface.blit(text2,text2Rect)
								self.update(text2Rect)
						elif e.key==13:
							flag=False
						elif e.key==8:
							self.surface.blit(self.bg,text2Rect,text2Rect)
							nom=nom[0:len(nom)-1]
							text2 = font.render(nom,1,mycolors.GREEN,mycolors.BLACK)
							self.update(text2Rect)
							self.surface.blit(text2,text2Rect)
							self.update(text2Rect)
				pygame.time.wait(100)
			if len(nom)==0:
				nom="Space Max"
			fic.write(str(self.score)+","+str(nom)+"\n")
			fic.close
		except:
			print("Impossible d'ouvir hight.txt / can't open file high.txt")

	def highscore_print(self):

		font=pygame.font.Font(None,24)
		font2=pygame.font.Font(None,14)
		y=0
		n=0
		self.break_high=False
		for score_iter in self.highscore:
			 if n==0:
				 self.surface.blit(self.bg2,self.bgRect2)
				 self.update(self.bgRect2)
			 n+=1
			 text1 = font.render(str(score_iter[0])+"  "+str(score_iter[1]),1,mycolors.YELLOW,mycolors.BLACK)
			 textpos = text1.get_rect()
			 y=y+32
			 textpos = textpos.move (int((self.width-textpos.width)/2),264+y)
			 self.surface.blit(text1,textpos)
			 self.update(textpos)
			 if n==4:
				 y=y+32
				 text1 = font2.render("P to see next / Q to Quit hight score",1,mycolors.GREEN,mycolors.BLACK)
				 textpos = text1.get_rect()
				 textpos = textpos.move (int((self.width-textpos.width)/2),264+y)
				 self.surface.blit(text1,textpos)
				 self.update(textpos)
				 self.pause()
				 n=0
				 y=0
			 if self.break_high==True:
				 break

	def option_ecran(self):

			self.surface.blit(self.bg,self.bgRect)
			pygame.display.update()
			jeu.ajoute_alien(5,6)
			self.option_blit()

	def option_blit(self):
			font=pygame.font.Font(None,16)
			phrase=[words.words[2][LANG],words.words[12][LANG]]
			i=0
			top=-12
			while i<=1:
				if i==0:
					textOption = font.render(phrase[i]+" : "+ str(FPS),1,mycolors.YELLOW,mycolors.BLACK)
				else:
					textOption = font.render(phrase[i],1,mycolors.GREEN,mycolors.BLACK)
				textOptionRect = textOption.get_rect()
				center=int((self.width-textOptionRect.width)/2)
				top+=textOptionRect.height
				textOptionRect=textOptionRect.move(center,top)
				textOptionRect.width+=50
				self.surface.blit(self.bg,textOptionRect,textOptionRect)
				self.update(textOptionRect)
				self.surface.blit(textOption,textOptionRect)
				self.update(textOptionRect)
				i+=1
			jeu.clock.tick(FPS)

	def dommage(self):
		'''
		Used to display the last post of the Game : SpaceMax is stronger than you...
		'''
		font = pygame.font.Font(None, 24)
		self.text1 = font.render(words.words[13][LANG], 1, mycolors.WHITE,mycolors.BLACK)
		self.text1pos=self.text1.get_rect()
		x=(self.width/2)-(self.text1pos.width/2)
		y=(self.height/2)-(self.text1pos.height/2)
		self.text1pos=self.text1pos.move(x,y)
		self.surface.blit(self.text1,self.text1pos)
		self.update(self.text1pos)
		pygame.time.delay(3000)

#__________________________________________________________________________________________________

class Bandeau(pygame.sprite.Sprite):

	global OS

	def __init__(self):

		pygame.sprite.Sprite.__init__(self)
		self.shield=pygame.Surface((32,8),SRCALPHA)  # Use for progress bar of the shield
		self.font = pygame.font.Font(None, 24)
		self.image=pygame.Surface((640,40))
		self.rect=self.image.get_rect()

		# Array of character use for display Extra Life
		self.extra=[""]*13
		self.timer=-1
		pygame.time.set_timer(USEREVENT+1, 300)
		self.ind=0

	def update(self):

		# Le bandeau du Jeu
		# The informations of the gamer
		self.text1 = self.font.render(words.words[6][LANG] + str(jeu.niveau) + "  " , 1, mycolors.BLUE_LIGHT,mycolors.BLACK)
		self.textpos1 = self.text1.get_rect()
		self.image.blit(self.text1, self.textpos1)

		self.text2 = self.font.render(words.words[7][LANG]+ str(jeu.vie) + "  " , 1, mycolors.WHITE,mycolors.BLACK)
		self.textpos2 = self.text2.get_rect()
		self.textpos2 =self.textpos2.move(130,0)
		self.image.blit(self.text2, self.textpos2)

		self.text3 = self.font.render(words.words[8][LANG] + str(jeu.extra_bombe) + "  ",1,mycolors.YELLOW,mycolors.BLACK)
		self.textpos3 = self.text3.get_rect()
		self.textpos3 = self.textpos3.move(260,0)
		self.image.blit(self.text3, self.textpos3)

		try:
			self.text4 = self.font.render(words.words[9][LANG] + str(vaisseau.power) + "  ",1,mycolors.GREEN,mycolors.BLACK)
		except:
			 self.text4 = self.font.render(words.words[9][LANG] ,1,mycolors.GREEN,mycolors.BLACK)
		self.textpos4 = self.text4.get_rect()
		self.textpos4 = self.textpos4.move(390,0)
		self.image.blit(self.text4, self.textpos4)

		self.text5 = self.font.render(words.words[10][LANG]+ str(jeu.score)+"  ",1, mycolors.RED,mycolors.BLACK)
		self.textpos5 = self.text5.get_rect()
		self.textpos5 = self.textpos5.move(520,0)
		self.image.blit(self.text5, self.textpos5)

		self.text6 = self.font.render(words.words[11][LANG] ,1, mycolors.GREEN,mycolors.BLACK)
		self.textpos6 = self.text6.get_rect()
		self.textpos6.top=21
		self.image.blit(self.text6, self.textpos6)

		self.shield_rect=self.shield.get_rect()
		self.shield_rect.top=self.textpos6.top+8
		self.shield_rect.left=self.textpos6.right

		# PRINT EXTRA LIFE

		self.ind+=1

		if jeu.extra_life==1:
			jeu.play_sound(jeu.sound_extra_life, 1)
			self.print_extra_life()
			jeu.extra_life=0
			self.timer=0
			self.clock=pygame.time.Clock()
			self.timer+=self.clock.tick(FPS)

		if self.timer>5000:
			self.erase_extra_life()
			self.timer=-1
		elif self.timer>=0:
			self.timer+=self.clock.tick(FPS)
			if OS!="WINDOWS":
				for event in pygame.event.get():
					if event.type == USEREVENT+1:
						if self.ind/2==self.ind/2.0:
							self.erase_extra_life()
						else:
							self.print_extra_life()
			else: # Nard'in Windows !
				if self.ind/2==self.ind/2.0:
					self.print_extra_life()
		try:
			if vaisseau.protected<=2:
				couleur=mycolors.RED
			elif vaisseau.protected<=4:
				couleur=mycolors.ORANGE
			elif vaisseau.protected<=6:
				couleur=mycolors.YELLOW
			else:
				couleur=mycolors.GREEN
			self.shield.fill(mycolors.BLACK)
			self.shield.fill(couleur,pygame.Rect(0,0,vaisseau.protected*4,8))
		except:
			pass
		self.image.blit(self.shield,self.shield_rect)

	def print_extra_life(self):

		self.extra[0]= self.font.render("E",1,mycolors.PINK,mycolors.BLACK)
		self.extra[1]= self.font.render("x",1,mycolors.YELLOW,mycolors.BLACK)
		self.extra[2]= self.font.render("t",1,mycolors.GREEN,mycolors.BLACK)
		self.extra[3]= self.font.render("r",1,mycolors.PINK,mycolors.BLACK)
		self.extra[4]= self.font.render("a",1,mycolors.YELLOW,mycolors.BLACK)
		self.extra[5]= self.font.render(" ",1,mycolors.BLACK,mycolors.BLACK)
		self.extra[6]= self.font.render("L",1,mycolors.PINK,mycolors.BLACK)
		self.extra[7]= self.font.render("i",1,mycolors.YELLOW,mycolors.BLACK)
		self.extra[8]= self.font.render("f",1,mycolors.GREEN,mycolors.BLACK)
		self.extra[9]= self.font.render("e",1,mycolors.PINK,mycolors.BLACK)
		self.extra[10]=self.font.render("!",1,mycolors.YELLOW,mycolors.BLACK)
		self.extra[11]=self.font.render("!",1,mycolors.GREEN,mycolors.BLACK)
		self.extra[12]=self.font.render("!",1,mycolors.PINK,mycolors.BLACK)

		start=140
		for character in self.extra:
			letter_pos=character.get_rect()
			letter_pos=letter_pos.move(start,21)
			start+=letter_pos.width
			self.image.blit(character, letter_pos)

	def erase_extra_life(self):
		blank=self.font.render("Extra Life !!!",1,mycolors.BLACK,mycolors.BLACK)
		self.image.blit(blank,blank.get_rect().move(140,21))
#__________________________________________________________________________________________________

class Bg (pygame.sprite.Sprite):

	def __init__(self):
		pygame.sprite.Sprite.__init__(self)
		self.image=jeu.bgscroll
		self.rect=self.image.get_rect()

	def update(self):

	   # For remenber : Height of bandeau (life,score,power info) : 40px

	   self.rect.bottom += 1
	   if self.rect.bottom >= self.rect.height:
		   self.rect.top=-(self.rect.height-480)

class Polygon(pygame.sprite.Sprite):
	def __init__(self,left=0,top=0):
		pygame.sprite.Sprite.__init__(self)
		jeu.allpolygon.add(self)
		
		self.image=pygame.Surface((160,120))
		
		# Number of tuple for a polygon
		self.nb_tuple=random.randint(3,12)
		
		self.coordonates=[]
		for i in range(self.nb_tuple):
			
			
			c=random.randint(0,160)
			l=random.randint(0,120)
			self.coordonates.append((c,l))

		color=(random.randint(0,255),random.randint(0,255),random.randint(0,255))
		pygame.draw.polygon(self.image, color, self.coordonates)
		self.rect=self.image.get_rect()
		self.rect.left=left
		self.rect.top=top
		#print (self.rect)
		# Remember the position
		self.x=self.rect.left
		self.y=self.rect.top
	
	def update(self):
		self.rect.bottom += 1
		if self.rect.top>480:
			pol=Polygon(self.x,-120)
			jeu.allpolygon.add(pol)
			self.kill()
#_______________________________________________________________________________
class Nepomuk(pygame.sprite.Sprite):

	def __init__(self):

		pygame.sprite.Sprite.__init__(self)

		self.image=jeu.nepomuk_img
		self.rect=self.image.get_rect()
		self.loto=random.randint(0,1)
		if self.loto==0:
			self.rect.left=jeu.width
			self.sens=-1
		else:
			self.rect.left=0
			self.sens=1
		self.rect.top=96

	def update(self):
		self.rect.left+=2*self.sens
		if self.rect.left>0 and self.rect.left<jeu.width:
			jeu.surface.blit(self.image,self.rect)
			if self.rect.colliderect(vaisseau.rect):
				randomize=random.randint(1,6)
				if randomize==1:
					vaisseau.power+=1
				elif randomize==2:
					jeu.bombe+=3
				elif randomize==3:
					jeu.shield+=1
				elif randomize==4:
					jeu.vie+=1
				elif randomize==5:
					if vaisseau.power>1:
						vaiseau.power-=1
				self.rect=None
		#print (jeu.nepomuk,jeu.timepower)
#_____________________________________________________
class Alien(pygame.sprite.Sprite):

	def __init__(self,lig,col,extra=False):

		pygame.sprite.Sprite.__init__(self)

		jeu.allalien.add(self)
		self.extra=extra
		self.indexplosion=0
		self.exploded=False
		
		# used for grow or shrink the alien 
		
		self.grow=1
		
		# Temps pour les tirs Aliens / Time for the shoots
		
		self.time_for_shoot=random.randint(0,2000)
		
		# Temps pour le bouclier / Time for the shield
		
		self.time_for_shield=random.randint(0,2000)
		
		self.invinsibility=False # only if shield is present
		
		if self.extra==False:
			
			# transfers the images of the aliens into the class
			
			self.fond=jeu.png2[jeu.niveau-1]
		else:
			
			# it's a extra alien !
			
			 self.fond=jeu.png2[13]
			 jeu.play_sound(jeu.sound_alien_attack,-1)
			 jeu.allextra.add(self)

		# La première image est prise comme référence pour le rectangle
		# the first image is use to define rect and image property, necessary in class sprite
		
		self.image=self.fond[0]
		self.rect=self.fond[0].get_rect()
		
		# Flag used to determine which image is blitted
		
		self.indice_image=-1

		self.r=32

		# Coordonnées de naissance / coordinates of birth
		
		self.x=lig
		self.y=col

		# Positionnement sur l'écran /
		
		self.rect.top=self.y
		self.rect.left=self.x

		########################################################################
		#   CARACTERE DES ALIENS / FEATURES OF ALIEN
		#
		# Neutre   : Reste sur sa ligne / cool alien
		# Nerveux  : Descend et remonte / nervous : up and down
		# Agressif : Peut attaquer le vaisseau / very nervous : can collide with ship
		# crazy : fait des cercles et tirs 2 fois / makes circles and it strikes two times
		# spirale  : they are kamikazes
		########################################################################

		if self.extra!=True:
			self.caractere=random.sample(["neutre","peu nerveux","nerveux","tres nerveux","agressif","crazy","spirale","crazy2"],1)
			#self.caractere=random.sample(["crazy2"],1)
		else:
			self.caractere=random.sample(["extra"],1)

		# A crazy or a spirale must be in these limits otherwhise it's an agressif
		
		if self.caractere[0]=="crazy" and self.y<96 or(self.x<64 or self.x>576):
			self.caractere[0]="agressif"

		if self.caractere[0]=="spirale" and self.y<96 or(self.x<64 or self.x>576):
			self.caractere[0]="agressif"
		
		#self.caractere[0]="neutre"
		
		# Certains aliens peuvent caché un cadeau...
		# Some aliens can have a surprise

		self.cadeau=False
		self.cadeau_type=0

		# Loterie pour attribuer le génome
		# lottery for ADN
		
		cadeau=random.randint(0,250)
		
		#--------------------------------------------------------------------------------------
		# Lottery for power depend of the current level
		#--------------------------------------------------------------------------------------
		
		# Power (self.cadeau_type==2) is distributed in regarding the current level
		
		if jeu.niveau<4: # under level 4, one chance on 250
			if cadeau==10:
				self.cadeau=True
				self.cadeau_type=2
		elif jeu.niveau>3 and jeu.niveau<8: # between level 4 and level 7, 2 chance on 250
			 if cadeau==10 or cadeau==100:
				self.cadeau=True
				self.cadeau_type=2
		else:
			if cadeau==10 or cadeau==100 or cadeau==200: # After level 7, 3 chances on 250
				self.cadeau=True
				self.cadeau_type=2
		
		# The others surprises
			   
		if cadeau==17: # I love this number...
			
			# 0 --> vie / life
			self.cadeau=True
			self.cadeau_type=0
			
		elif cadeau==9 or cadeau==3 or cadeau==21:
			
			# 1 --> 1 Bombe du vaisseau / bomb for space ship
			
			self.cadeau=True
			self.cadeau_type=1
			
		elif cadeau>=50 and cadeau<=60:
			
			 # 3 --> Bombe Alien
			 
			self.cadeau=True
			self.cadeau_type=3
			
		elif cadeau>60 and cadeau<=63:
			
			 # 4 --> Bouclier / shield
			 
			self.cadeau=True
			self.cadeau_type=4
			
		elif cadeau>245:
			
			# 5 --> Invinsibility
			
			self.cadeau=True
			self.cadeau_type=5
		
		self.coup=0

		self.sensx=random.sample([-1,1],1)[0] # horizontal movement
		self.sensy=0 # Pas de mouvements verticaux / at this step no vertical movement

	def update(self,pas=4):

		self.time_for_shoot+=jeu.clock.get_time()
		self.time_for_shield+=jeu.clock_shield.get_time()
		#print(self.time_for_shield)
		
		if len(jeu.allextra)==0:
			jeu.sound_alien_attack.stop()

		# Determine le type de bombe / Determine the type of bomb
		
		if self.caractere[0]!="crazy":
			if jeu.niveau==1 or jeu.niveau==6:
				type_bombe=10
			elif jeu.niveau==2 or jeu.niveau==7:
				type_bombe=20
			elif jeu.niveau==3 or jeu.niveau==8 or jeu.niveau==11:
				type_bombe=30
			elif jeu.niveau==5 or jeu.niveau==9 or jeu.niveau==12:
				type_bombe=40
			elif jeu.niveau==4 or jeu.niveau==10 or jeu.niveau==13:
				type_bombe=50
		else:
				# A crazy can choose his weapon
				type_bombe=random.sample([10,20,30,40,50],1)[0]
				
		##################################################################################      
		# Tirs des Aliens après un certains temps / Alien shoot a bomb after a duration
		##################################################################################
				 
		if self.time_for_shoot>(5000-jeu.niveau*200) and jeu.niveau<7 and self.caractere[0]!="crazy":
			self.time_for_shoot=0
			bombe=BombeAlien(type_bombe,self.rect)
			jeu.allbombealien.add(bombe)
			
		elif self.time_for_shoot>3000 and jeu.niveau>=7 and jeu.niveau<10 and self.caractere[0]!="crazy":
			self.time_for_shoot=0
			bombe=BombeAlien(type_bombe,self.rect)
			jeu.allbombealien.add(bombe)
		elif self.time_for_shoot>3000 and (jeu.niveau>=10 or self.caractere[0]=="crazy"or self.caractere[0]=="crazy2"):
			self.time_for_shoot=0
			bombe=BombeAlien(type_bombe,self.rect)
			jeu.allbombealien.add(bombe)
			self.tictac=0
			self.laps=pygame.time.Clock()
			self.laps.tick(FPS)
		try:
			self.tictac+=self.laps.get_time()
			if self.tictac>200:
				bombe=BombeAlien(type_bombe,self.rect)
				jeu.allbombealien.add(bombe)
				self.tictac=0
				self.laps=None
			#print(self.tictac," ",nb)
		except:
			pass

		########################################################################
		# The shield
		########################################################################
		if self.time_for_shield>7000 and self.time_for_shield<9000:
			pygame.draw.circle(jeu.surface,mycolors.WHITE,(self.rect.left+16,self.rect.top+16),32,1)
			self.invinsibility=True
		elif self.time_for_shield>9000:
			self.time_for_shield=0
			self.invinsibility=False
			
		self.pas=pas
		
		# Rotation des images alien à afficher
		# loop for the images to display

		if self.indice_image<len(self.fond)-1:
			self.indice_image+=1
			self.image=self.fond[self.indice_image]
		else:
			self.indice_image=-1

		# Mouvement des Aliens en fonction du caractère
		# determine the movement of the alien according to of his caracteristic

		########################################################################
		# Here is the section to handle the movements
		########################################################################

		# Features for all aliens except crazy and spirale alien
		# Minimal movement for cool alien
		
		if self.rect.right>=jeu.width:
			self.sensx=-1
		elif self.rect.left<=0:
			self.sensx=1
			
		# Peu Nerveux / little nervous, cool
		if self.caractere[0]=="peu nerveux":
			if self.rect.top<=self.y:
				self.sensy=1
			elif self.rect.top>=self.y+16:
				 self.sensy=-1
				 
		# Nerveux / nervous
		elif self.caractere[0]=="nerveux":
			if self.rect.top<=self.y:
				self.sensy=1
			elif self.rect.top>=self.y+32:
				 self.sensy=-1
				 
		# Tres Nerveux / very nervous
		elif self.caractere[0]=="tres nerveux":
			if self.rect.top<=self.y:
				self.sensy=1
			elif self.rect.top>=224:
				 self.sensy=-1
				 
		# Agressif / very nervous : can collide with ship
		elif self.caractere[0]=="agressif":
			if self.rect.top<=self.y:
				self.sensy=1
			elif self.rect.top>=448:
				 self.sensy=-1
				 
		# extra is kamikaze
		elif self.caractere[0]=="extra":

			if self.rect.top<478:
				if jeu.niveau<10:
					self.rect.top+=2
				else:
					self.rect.top+=4
			else:
				self.rect.top=self.y
			diff=math.fabs(self.rect.left-vaisseau.rect.left)
			if self.rect.left<=vaisseau.rect.left:
				if diff>4:
					self.rect.left+=4
				else:
					self.rect.left+=diff
			elif self.rect.left>vaisseau.rect.left:
				if diff>4:
					self.rect.left-=4
				else:
					self.rect.left-=diff

		# Move where not crazy, spirale or extra
		if self.caractere[0]!="crazy" and self.caractere[0]!="spirale" and self.caractere[0]!="extra":
			self.rect=self.rect.move(pas*self.sensx,self.sensy)
			
		# Crazy or Crazy2
		if self.caractere[0]=="crazy" or self.caractere[0]=="crazy2":
			self.cx=self.r*math.cos(self.r)
			self.cy=self.r*math.sin(self.r)
			self.rect.left=self.x+self.cx
			self.rect.top=self.y+self.cy
			if self.r<100.0 and (self.rect.top>44 and self.rect.top<448 and self.rect.left>32 and self.rect.left<608):
				self.r+=.1
			else:
				self.r=1
			
			if self.caractere[0]=="crazy2":
				if self.rect.width<=16:
					self.grow=-1
				elif self.rect.width>=32:
					self.grow=1
					
				self.rect.width-=self.grow
				self.rect.height-=self.grow
				self.rect=self.rect.fit((self.rect.left,self.rect.top,self.rect.width,self.rect.height))
				self.image=pygame.transform.scale(self.image,(self.rect.width,self.rect.height))

		elif self.caractere[0]=="spirale":
			if self.rect.right>=jeu.width:
				self.sensx=-1
			elif self.rect.left<=0:
				self.sensx=1
			self.cx=64*math.cos(self.r)
			self.cy=64*math.sin(self.r)
			self.rect.left=self.x+self.cx*self.sensx
			self.rect.top=self.y+self.cy
			if self.r<6.3:
				self.r+=.1
				self.x+=.5*self.sensx
			else:
				self.r=0
				
		# Test Collision Alien et Vaisseau
		# test if an collision between ship and alien appears
		if self.rect.colliderect(vaisseau.rect):
			self.coup=99
			if self.exploded==False: # Mean it collide the ship
				if vaisseau.invinsibility==False:
					vaisseau.explosion()
				self.exploded=True

		if jeu.nb_extra_bombe==1 or self.coup>=jeu.niveau:
			if self.indexplosion<5:
				self.image=jeu.alien_explosion[self.indexplosion]
				self.indexplosion+=1
			else:
				self.indexplosion=-1
				jeu.score+=1*jeu.niveau
				if self.caractere[0]=="agressif":
						  jeu.score+=10
				jeu.allalien.remove(self)
				if self.extra==True:
					jeu.allextra.remove(self)
				self.explosion()
				jeu.play_sound(jeu.sound_alien_expl)
				if len(jeu.allalien)==0:
					jeu.nb_extra_bombe=0
					jeu.allextra.empty()

	def explosion(self):

		if self.cadeau==True:
			bonus=Cadeau(self.cadeau_type,self.rect.top,self.rect.right)
			jeu.allcadeau.add(bonus)
		
		# Add new extra alien only when not collided with ship
		# self.exploded==False in this case
		
		if self.caractere[0]=="spirale" and self.exploded==False:
			if jeu.niveau<=4:
				n=2
			elif jeu.niveau<=8:
				n=3
			else:
				n=4
			for i in range(n):
				objet_alien=Alien(self.x+i*64,self.y+i*32,extra=True)
				jeu.allalien.add(objet_alien)
#_______________________________________________________________________________
class Cadeau(pygame.sprite.Sprite):

	def __init__(self,type_cadeau,top,right):

		pygame.sprite.Sprite.__init__(self)

		self.type_cadeau=type_cadeau
		if self.type_cadeau==0:
			self.image=jeu.cadeau
		elif self.type_cadeau==1:
			self.image=jeu.bombe
		elif self.type_cadeau==2:
			self.image=jeu.power
		elif self.type_cadeau==3:
			self.image=jeu.piege
		elif self.type_cadeau==4:
			self.image=jeu.shield
		elif self.type_cadeau==5:
			self.image=jeu.invinsibility       

		self.rect=self.image.get_rect()
		self.rect.top=top
		self.rect.right=right

	def update(self):

		# Si c'est un piège, limite à 448 pour explosion
		# set the limit of the fall for the surprises

		if self.type_cadeau!=3:
			limite=480
		else:
			limite=448

		# Chute de l'objet / fall of the object
		if self.rect.top<limite:
			self.rect=self.rect.move(0,4)
		else:
			self.kill()
			# Explosion du piege à l'arrivée
			# if the suprise is a trap (tnt), explosion at the end of the downfall
			if self.type_cadeau==3:
			   piege=Piege(self.rect.top,self.rect.right)

		# Test colision vaiseau et cadeaux / collide surprises and ship

		if self.rect.colliderect(vaisseau.rect):
			
			# vie / life
			
			if self.type_cadeau==0:
				jeu.vie+=1
				jeu.play_sound(jeu.sound_vie)
				jeu.score+=100
				
			# Bombe / bomb
			
			elif self.type_cadeau==1:
				jeu.extra_bombe+=1
				jeu.play_sound(jeu.sound_bombe)
				jeu.score+=50
				
			# Power
			
			elif self.type_cadeau==2:
				jeu.score+=25
				vaisseau.power+=1
				jeu.play_sound(jeu.sound_power,5)
				jeu.score+=25
				
			# Colission avec un piege / Collision with a trap (tnt)
			
			elif self.type_cadeau==3 and vaisseau.invinsibility==False:
				vaisseau.explosion()
				
			# Collide with a shield
			
			elif self.type_cadeau==4:
				if vaisseau.protected<8:
					jeu.play_sound(jeu.sound_shield)
					jeu.score+=25
					vaisseau.protected+=1
				else:
					jeu.extra_life=1
					jeu.score+=500
					jeu.vie+=1
					
			# Invinsibilité / invinsibility
			
			elif self.type_cadeau==5:
					vaisseau.invinsibility_duration=10000
					vaisseau.invinsibility=True
			self.kill()
#_______________________________________________________________________________
class Piege(pygame.sprite.Sprite):

	def __init__(self,top,right):

		pygame.sprite.Sprite.__init__(self)

		# La première image est prise commme référence du rectangle
		# The first image is used to set the rect
		
		self.image=jeu.piege_expl[0]
		self.rect=jeu.piege_expl[0].get_rect()

		self.rect.top=top
		self.rect.right=right+96
		self.update()
		touche=False
		for image in jeu.piege_expl:
			jeu.surface.blit(image,self.rect)
			jeu.update(self.rect) # improve here
			
			# Test collision des pieges et du vaisseau
			# Test collision between ship and trap (tnt)
			
			if self.rect.colliderect(vaisseau.rect):
				touche=True
		if touche==True:
			vaisseau.protected-=6
			if vaisseau.protected<=0:
				self.kill()
				vaisseau.explosion()
			bandeau.shield.fill(mycolors.BLACK)

		pygame.time.delay(30)
		jeu.play_sound(jeu.sound_alien_expl)
#_______________________________________________________________________________
class BombeAlien (pygame.sprite.Sprite):

	def __init__(self,type_bombe,rect):

		# rect est le rect de l'alien
		# rect is the rect of the alien

		pygame.sprite.Sprite.__init__(self)

		self.type_bombe=type_bombe
		
		# Charge l'image du tir
		# Load the image of the bomb
		
		self.image=eval("jeu.alien_bomb"+str(type_bombe))
		self.rect=self.image.get_rect()
		
		# position la surface au dessous de l'alien
		# display the bomb under the alien
		
		x=(rect.width-self.rect.width)/2
		self.rect=self.rect.move(rect.left+x,rect.top+32)

	def update(self):

			if jeu.niveau<3:
				stepx=0
				stepy=4
			elif jeu.niveau>=3 and jeu.niveau<=6:
				stepx=0
				stepy=6
			elif jeu.niveau>=6 and jeu.niveau<=9:
				stepx=0
				stepy=8
			elif jeu.niveau>=9 and jeu.niveau<=12:
				stepx=0
				stepy=10
			else:
				stepx=0
				stepy=12
			self.rect=self.rect.move(stepx,stepy)
			if self.rect.top>480:
				self.kill()
			if vaisseau.invinsibility==False:
				if self.rect.colliderect(vaisseau.rect):
					
					# Decrease protection
					
					if self.type_bombe==10:
						vaisseau.protected-=1
					elif self.type_bombe==20:
						vaisseau.protected-=2
					elif self.type_bombe==30:
						vaisseau.protected-=3
					elif self.type_bombe==40:
						vaisseau.protected-=4
					elif self.type_bombe==50:
						vaisseau.protected-=5
					self.kill()
					
					# Test if the ship is exploded
					
					if vaisseau.protected<0:
						vaisseau.explosion()
					else:
						vaisseau.alert()
						jeu.play_sound(jeu.sound_boss_affected)
						
#_______________________________________________________________________________
class Gun(pygame.sprite.Sprite):
	def __init__(self,type):
		pygame.sprite.Sprite.__init__(self)
		self.type=type
		if self.type==1: # 1 Left Gun 2 Right Gun
			self.image=jeu.vaisseau07
		else:
			self.image=jeu.vaisseau08
		self.rect=self.image.get_rect()
	
	def update(self):
		if self.type==1:
			self.rect.right=vaisseau.rect.left
		else:
			self.rect.left=vaisseau.rect.right
		self.rect.top=vaisseau.rect.top+10
		
class Vaisseau(pygame.sprite.Sprite):

	def __init__ (self):

		pygame.sprite.Sprite.__init__(self)

		self.power=1
		self.protected=0 # the shield between 0 to 8...
		self.vaisseau_explosion=[pygame.Surface] * 12
		self.image=jeu.vaisseau01
		self.rect=self.image.get_rect()
		self.invinsibility_duration=5000
		self.laps_invinsibility=0
		self.clock_invinsibility=pygame.time.Clock()
		
		self.laps_blink=0
		self.blink=False
		self.invinsibility=False
		
	def pos(self,x,y):
		self.rect=self.rect.move(x,y)

	def raz(self):
		self.rect.top=0
		self.rect.right=0
		self.pos(304,448)
		jeu.surface.blit(self.image,self.rect)

	def update(self):
		
		self.clock_invinsibility.tick()
		if self.invinsibility==True:
			if self.laps_invinsibility<self.invinsibility_duration:
				self.laps_invinsibility+= self.clock_invinsibility.get_time()
				if self.laps_blink<500:
					self.laps_blink+=self.clock_invinsibility.get_time()
					pass
				else:
					self.blink=not self.blink
					self.laps_blink=0  
			else:
				self.laps_invinsibility=0
				self.laps_blink=0
				self.invinsibility=False
				self.blink=False
				
		if self.blink==True:
			self.image=jeu.vaisseau09
		else:
			self.image=jeu.vaisseau01 
		
		if self.power>9:
			if len(jeu.allgun)<2:
				gun1=Gun(1)
				gun2=Gun(2)
				jeu.allgun.add(gun1)
				jeu.allgun.add(gun2)
		else:
			jeu.allgun.empty()
			
		test=pygame.key.get_pressed()
		
		if test[pygame.K_SPACE]: 
			self.tir_vaisseau()

		if test[pygame.K_LEFT]:
			if self.rect.left>0:
				self.rect.left-=8
			else:
				
				# Si on est arrivé à gauche on repart à droite
				
				self.rect=self.rect.move(608,0)
			if test[pygame.K_SPACE]:
				self.tir_vaisseau()

		if test[pygame.K_RIGHT]:
			if self.rect.right<640:
				self.rect.left+=8
			else:
				
				# Si on est arrivé à droite on repart à gauche
				
				self.rect=self.rect.move(-608,0)
			if test[pygame.K_SPACE]:
				self.tir_vaisseau()

		if test[pygame.K_UP]:
			if self.rect.top>40:
				self.rect.top-=8
			if test[pygame.K_SPACE]:
				self.tir_vaisseau()

		if test[pygame.K_DOWN]:
			if self.rect.top<448:
				self.rect.top+=8
			if test[pygame.K_SPACE]:
				self.tir_vaisseau()

	def tir_vaisseau(self):

		# Gestion des Tirs / the fire of the ship
	   
		if self.power==1:
			self.power1(5)
			
			# show the dead head
			
			if self.blink==True:
				self.image=jeu.vaisseau09
			else:
				self.image=jeu.vaisseau02
		elif self.power==2:
			 self.power2(15)
			 if self.blink==True:
				self.image=jeu.vaisseau09
			 else:
				 self.image=jeu.vaisseau03
			 #jeu.surface.blit(jeu.vaisseau03,self.rect)
			 
		elif self.power>=3 and self.power<=5:
			self.power3(25)
			if self.blink==True:
				self.image=jeu.vaisseau09
			else:
				self.image=jeu.vaisseau04
			#jeu.surface.blit(jeu.vaisseau04,self.rect)
		elif self.power==6:
			self.power3(50)
			if self.blink==True:
				self.image=jeu.vaisseau09
			else:
				self.image=jeu.vaisseau04
			#jeu.surface.blit(jeu.vaisseau04,self.rect)
		elif self.power>=7 and self.power<=9:
			self.power4(70)
			if self.blink==True:
				self.image=jeu.vaisseau09
			else:
				self.image=jeu.vaisseau04
		elif self.power>9:
			self.power5(100)
		
	def power1(self,nb_munition):
		if len(jeu.allmunition)<nb_munition:
			munition=Munition(1,14)
			jeu.allmunition.add(munition)

	def power2(self,nb_munition):

		if len(jeu.allmunition)<nb_munition:
			self.power1(nb_munition)
			munition=Munition(3,4)
			jeu.allmunition.add(munition)
			munition=Munition(3,24)
			jeu.allmunition.add(munition)

	def power3(self,nb_munition):

		if len(jeu.allmunition)<nb_munition:
			self.power1(nb_munition)
			self.power2(nb_munition)
			munition=Munition(2,0)
			jeu.allmunition.add(munition)
			munition=Munition(2,31)
			jeu.allmunition.add(munition)

	def power4(self,nb_munition):
		if len(jeu.allmunition)<nb_munition:
			self.power1(nb_munition)
			self.power2(nb_munition)
			self.power3(nb_munition)
			munition=Munition(4,0)
			jeu.allmunition.add(munition)
			munition=Munition(4,31)
			jeu.allmunition.add(munition)
			
	def power5(self,nb_munition):
		if len(jeu.allmunition)<nb_munition:
			self.power1(nb_munition)
			self.power2(nb_munition)
			self.power3(nb_munition)
			munition=Munition(4,0)
			jeu.allmunition.add(munition)   
			munition=Munition(4,31)
			jeu.allmunition.add(munition)
			if len(jeu.allmunition2)<10:
				munition=Munition(5,-6)
				jeu.allmunition2.add(munition)
				munition=Munition(6,37)
				jeu.allmunition2.add(munition)
					
	# Bomb handler
	
	def tir_bombe(self):

		if jeu.extra_bombe>0 and len(jeu.allalien)!=0 and jeu.nb_extra_bombe==0:
			jeu.nb_extra_bombe=1
			jeu.extra_bombe-=1
		try:
		  if jeu.extra_bombe>0 and boss.force>0 and jeu.nb_extra_bombe==0:
			jeu.nb_extra_bombe=1
			jeu.extra_bombe-=1
			boss.force-=50
			jeu.play_sound(jeu.sound_boss_cry)
		except:
		  pass

	# Explosion du vaisseau / ship's explosion
	
	def explosion(self):
		self.invinsibility=True
		
		jeu.play_sound(jeu.sound_vaisseau_expl)
		if self.protected<=0:
			self.protected=random.randint(2,9)
		if self.power>1:
			self.power-=1
		else:
			self.power=1
		jeu.vie-=1
		for image in jeu.vaisseau_explosion:
			jeu.surface.blit(image,self.rect)
			jeu.update(self.rect) # improve here
			jeu.play_sound(jeu.sound_vaisseau_expl)
			pygame.time.delay(50)

	def alert(self):
		jeu.surface.blit(jeu.vaisseau05,self.rect)
		jeu.play_sound(jeu.sound_alert)
		jeu.surface.blit(jeu.vaisseau06,vaisseau.rect)
		jeu.play_sound(jeu.sound_alert)
		pygame.time.delay(50)
#_______________________________________________________________________________
class Munition(pygame.sprite.Sprite):

	def __init__(self,type,pos):

		pygame.sprite.Sprite.__init__(self)
		
		self.type=type
		self.pos=pos
		self.sens=self.sens2=1
		
		if self.type==1:
			self.image=jeu.munition01
		elif self.type==2:
			self.image=jeu.munition02
		elif self.type==3:
			self.image=jeu.munition03
		elif self.type==4:
			self.image=jeu.munition04
		elif self.type==5:
			self.image=jeu.munition05
		elif self.type==6:
			self.image=jeu.munition06
			
		self.rect=self.image.get_rect()
		
		# position la munition la surface au dessus du vaisseau
		# Blit the munition onto the ship
		
		self.rect.left=vaisseau.rect.left
		self.rect=self.rect.move(self.pos,vaisseau.rect.top-2)
		jeu.surface.blit(self.image,self.rect)

	def update(self):
		
		if self.type<=3:
			self.rect=self.rect.move(0,-16)
		elif self.type==4:
			if self.pos==0:
				self.rect=self.rect.move(-4*self.sens,-16)
			else:
				self.rect=self.rect.move(4*self.sens,-16)
				
		elif self.type==5:
			if self.rect.left<16 or self.rect.right>624:
				self.sens2*=-1
				if self.image==jeu.munition05:
					self.image=jeu.munition06
				else:
					self.image=jeu.munition05
			self.rect=self.rect.move(-8*self.sens2,-2)
			
		elif self.type==6:
			if self.rect.left<16 or self.rect.right>624:
				self.sens2*=-1
				if self.image==jeu.munition05:
					self.image=jeu.munition06
				else:
					self.image=jeu.munition05
			self.rect=self.rect.move(8*self.sens2,-2)
			
		if self.rect.top<32 or self.rect.left<1 or self.rect.left>jeu.width:
			self.kill()
			
		# Test Colission avec Alien !!!
		
		test=pygame.sprite.spritecollide(self,jeu.allalien,0, collided = None)
		if (test!=[]):
			for alien in test:
				if alien.invinsibility==False:
					jeu.score+=1*jeu.niveau
					if self.type<=3:
						alien.coup+=1
						jeu.play_sound(jeu.sound_alien_cry)
					elif self.type==4:
						alien.coup+=5
					else:
						alien.coup=jeu.niveau
						
		# Section to test collision with the All the Boss
		
		try:
			test=pygame.sprite.spritecollide(self,jeu.allboss,0, collided = None)
			if (test!=[]):
				for boss in test:
					if self.type<=3:
						boss.force-=1
					elif self.type==4:
						boss.force-=2
					jeu.play_sound(jeu.sound_boss_affected)
					jeu.score+=10
					self.kill()
					if boss.force<=0:
						boss.explosion()
					elif self.type>=5 and self.type<=6:
						boss.force-=20
						jeu.play_sound(jeu.sound_boss_affected)
						jeu.score+=10
		except:
			pass

class Boss(pygame.sprite.Sprite):

	def __init__(self):
		pygame.sprite.Sprite.__init__(self)
		jeu.allboss.add(self)
		self.ind=0
		self.image=jeu.boss[self.ind]
		self.rect=self.image.get_rect()
		self.rect= self.rect.move(random.randint(100,540),random.randint(80,260))
		self.force=jeu.niveau*100
		self.time_for_shoot=0
		self.coup=0
		self.sensx=4*random.sample([-1,1],1)[0]
		self.sensy=4*random.sample([-1,1],1)[0]
		self.grow=1 # used for grow or shrink the Boss


	def update(self):
	
		if self.force<=0: 
			self.explosion()
		font = pygame.font.Font(None, 16)
		spaces=32*" "
		forceallboss=0
		for boss in jeu.allboss:
			forceallboss+=boss.force
			self.info=font.render(spaces+"Boss Force : " + str(forceallboss) + spaces, 1, mycolors.YELLOW,mycolors.RED)
			self.infoRect=self.info.get_rect()
			self.infoRect.top=23
			self.infoRect.left=((jeu.width-self.infoRect.width)/2)
			
			# Blit force info
			
			if self.force>=0:
				jeu.surface.blit(self.info, self.infoRect)

			# Refresh clock for shoot
			
			self.time_for_shoot+=jeu.clock.get_time()

			if self.rect.right>=jeu.width:
				self.sensx=-1
			elif self.rect.left<=0:
				self.sensx=1
			if self.rect.top<50:
				self.sensy=1
			elif self.rect.top>=250:
				self.sensy=-1
			self.rect=self.rect.move(self.sensx,self.sensy)

			# if extra bomb, rotation of the image
			
			if jeu.nb_extra_bombe==1:
				if self.ind<3:
					self.ind+=1
				else:
					self.ind=0
			else:
				self.ind=0
			self.image=jeu.boss[self.ind]

			if self.rect.width<=24:
				self.grow=-1
			elif self.rect.width>=64:
				self.grow=1

			self.rect.width-=self.grow
			self.rect.height-=self.grow

			if jeu.niveau>3:
				self.rect=self.rect.fit((self.rect.left,self.rect.top,self.rect.width,self.rect.height))
				self.image=pygame.transform.scale(self.image,(self.rect.width,self.rect.height))

			# Blit boss
			
			jeu.surface.blit(self.image, self.rect)

			# Test if it's the moment to shoot
			
			tps=3000-(jeu.niveau*50)
			if self.time_for_shoot>tps:
				self.time_for_shoot=0
				bombe=BombeBoss(random.randint(1,2),self.rect)
				jeu.allbombealien.add(bombe)

	def explosion(self):
		jeu.surface.blit(jeu.bg,self.rect,self.rect)
		#jeu.update(self.rect)
		jeu.score+=50*jeu.niveau
		self.kill()
#_______________________________________________________________________________
class BombeBoss(pygame.sprite.Sprite):


	def __init__(self,id,rect):
	
	# id is the type of bomb
	# rect is the rect of the boss

		pygame.sprite.Sprite.__init__(self)

		# Set the speed of the fall of the bombs
		
		if jeu.niveau<=8:
			multi=1
		else:
			multi=2

		self.id=id

		if self.id==1:
			self.image=jeu.bombe_boss01
			self.sensx=random.randint(-4*multi,4*multi)
		elif self.id==2:
			self.image=jeu.bombe_boss02
			self.sensx=0

		self.rect=self.image.get_rect()

		# position la surface au dessous du Boss
		# display under the boss
		
		self.rect=self.rect.move(rect.left+16,rect.top+64)
		jeu.surface.blit(self.image,self.rect)


	def update(self):

		if self.rect.right>=jeu.width:
			self.sensx=-1*self.sensx
		elif self.rect.left<=0:
			self.sensx=-1*self.sensx

		self.rect=self.rect.move(self.sensx,4)
		jeu.surface.blit(self.image,self.rect)

		if self.rect.top>480 and self.id==1:
			jeu.allbombealien.remove(self)
		elif self.rect.top>448 and self.id==2:
			jeu.allbombealien.remove(self)
			piege=Piege(self.rect.top,self.rect.right)

		if vaisseau.invinsibility==False:
			if self.rect.colliderect(vaisseau.rect):
				self.kill()
				vaisseau.explosion()
				vaisseau.invinsibility=True

#-------------------------------------------------------------------------------
#                              end classes
#_______________________________________________________________________________

def keyboard():

  # Gestion des evenements claviers / Keyboard
  
  pygame.event.get(pygame.KEYDOWN)
  if pygame.key.get_pressed()[K_SPACE]:
	  vaisseau.update()
  elif pygame.key.get_pressed()[112]:
	  jeu.pause()
  elif pygame.key.get_pressed()[97] or pygame.key.get_pressed()[113]:
	  jeu.vie=0
  elif pygame.key.get_pressed()[98]:
		vaisseau.tir_bombe()
  elif pygame.key.get_pressed()[K_ESCAPE]:
	  sys.exit()
  elif pygame.key.get_pressed()[K_f]:
	  jeu.toogle()
  else:
	   vaisseau.update()

def test_bomb():
	if  jeu.nb_extra_bombe==1 and jeu.extra_bombe_value>50:
		jeu.extra_bombe_value=0
		jeu.nb_extra_bombe=0
	elif jeu.nb_extra_bombe==1:
		jeu.extra_bombe_value+=1

def environement():
	dir=os.getcwd()
	#print(dir)
	myscript=sys.argv[0]
	#print(myscript)
	mydir=os.path.dirname(myscript)
	#print(mydir)
	try:
		os.chdir(mydir)
	except:
		pass
		
def CreatePolygon():
	
	#
	# Ajoute les polygones initiaux (Largeur 160 Hauteur 120)
	# 5 lignes de 4 polygones. La 1ere ligne commence à -120 et est donc invisible au départ
	#
	
	for y in range(5):
		for i in range(4):
			pol=Polygon(160*i,120*y)
			jeu.allpolygon.add(pol)
			
#-------------------------------------------------------------------------------
#                              End functions
#_______________________________________________________________________________

environement()
jeu=Jeu()

# Boucle Principale / Main loop

fin=False
while fin==False:

	CreatePolygon()	
	
	# Boucle MENU / Menu loop
	
	pygame.font.init()
	choix=-1
	while choix!=0:
		
		pygame.time.Clock().tick(FPS)
		jeu.surface.blit(jeu.bg2,jeu.bgRect2)
		jeu.update(jeu.bgRect2)
		
		joemenu=slidemenu.menu([
				 words.words[0][LANG],
				 words.words[1][LANG],
				 words.words[2][LANG],
				 words.words[3][LANG],
				 words.words[4][LANG],
				 words.words[44][LANG],
				 words.words[5][LANG],
				 ],
				 font1    = pygame.font.Font('./slidemenu/BeteNoirNF.ttf',20),
				 font2    = pygame.font.Font('./slidemenu/BeteNoirNF.ttf',25),
				 tooltipfont= pygame.font.Font('./slidemenu/Roboto-MediumItalic.ttf',12),
				 color1  = (255,80,40),
				 cursor_img = pygame.image.load("./graph/nepomuk.png"),
				 light    = 9,
				 centerx=320,
				 y=240
				 )
		choix=joemenu[1]
		
		# High Score
		
		if choix==1:
			jeu.highscore_print()
			if jeu.break_high==True:
				choix=-1
			while choix==1:
				pygame.time.wait(100)
				for event in pygame.event.get():
					if event.type == pygame.KEYDOWN:
						if event.key==97 or event.key==113:
							choix=-1
		# Speed
		
		if choix==2:
			jeu.option_ecran()
			pygame.key.set_repeat(10,50)
			vaisseau=Vaisseau()
			while choix==2:
				jeu.clock.tick(FPS)
				for event in pygame.event.get():
					if event.type == pygame.KEYDOWN:
						if event.key==97 or event.key==113  or event.key==13 or event.key==K_ESCAPE:
							choix=-1
						elif event.key==275:
							FPS+=1
							jeu.option_blit()
						elif event.key==276:
							FPS-=1
							jeu.option_blit()

				jeu.allalien.update()
				jeu.allalien.draw(jeu.surface)
				jeu.allbombealien.update()
				jeu.allbombealien.draw(jeu.surface)
				pygame.display.update()
				jeu.allbombealien.clear(jeu.surface, jeu.bg)
				jeu.allalien.clear(jeu.surface, jeu.bg)
			jeu.allalien.empty()
			
		# Generic
		
		if choix==3:
			scroll=generic.Scrolling([
									  (words.words[15][LANG],"c",24),
									  
									  (words.words[16][LANG],"c",12),
									  (words.words[17][LANG],"c",16), # Guido
									  (words.words[18][LANG],"c",14),
									  
									  (words.words[19][LANG],"c",12),
									  (words.words[20][LANG],"c",16), # Pygame
									  (words.words[21][LANG],"c",14),
									  (words.words[22][LANG],"c",12),
									  
									  (words.words[23][LANG],"c",12), # Sounds
									  (words.words[24][LANG],"c",16),
									  (words.words[25][LANG],"c",14),
									  (words.words[26][LANG],"c",12),
									  
									  (words.words[27][LANG],"c",16), # Josmiley
									  (words.words[28][LANG],"c",14),
									  (words.words[29][LANG],"c",12),
									  (words.words[30][LANG],"c",12),
									  
									  (words.words[31][LANG],"c",18), # Maya and Gabriel
									  (words.words[32][LANG],"c",14),
									  
									   (words.words[33][LANG],"c",12), 
									   (words.words[34][LANG],"c",16), # All guys
									   
									   (words.words[35][LANG],"c",12),
									   (words.words[36][LANG],"c",12),
									   (words.words[37][LANG],"c",12),
									   (words.words[38][LANG],"c",12),
									   (words.words[39][LANG],"c",12),
									   (words.words[40][LANG],"c",12),
									   
									  (words.words[41][LANG],"c",18), # SpaceMax    
									  (words.words[42][LANG],"c",14),
									  (words.words[43][LANG],"c",10),
									  ],
									 (255,255,255),jeu.surface,None)
			scroll.populate()
			
		# Option Langue / Langage
		
		if choix==4:
			if LANG==0:LANG=1
			else:LANG=0
			
		# Option Défilement / Scrolling
		
		if choix==5:
			choix2=0
			while choix2!=2:
				if choix2==0:
					jeu.surface.blit(jeu.bgscroll,jeu.bgRect)
					jeu.update(jeu.bgRect)
					jeu.optionScroll=0
				elif choix2==1:
					jeu.surface.fill(mycolors.BLACK)
					#jeu.allpolygon.update()
					jeu.allpolygon.draw(jeu.surface)
					pygame.display.flip()
					jeu.optionScroll=1

				joemenu2=slidemenu.menu([
					 words.words[45][LANG],
					 words.words[46][LANG],
					 words.words[5][LANG]
					 ],
					 font1    = pygame.font.Font('./slidemenu/BeteNoirNF.ttf',20),
					 font2    = pygame.font.Font('./slidemenu/BeteNoirNF.ttf',25),
					 tooltipfont= pygame.font.Font('./slidemenu/Roboto-MediumItalic.ttf',12),
					 color1  = (255,80,40),
					 cursor_img = pygame.image.load("./graph/nepomuk.png"),
					 light    = 9,
					 centerx=320,
					 y=240
					 )
				choix2=joemenu2[1]

		# System exit
		
		if choix==6 or choix==None:
			choix=0
			sys.exit()

	#---------------------------------------------------------------------------
	#   The Game
	#---------------------------------------------------------------------------

	pygame.key.set_repeat(1,1)

	# Le vaisseau / the ship
	vaisseau=Vaisseau()
	vaisseau.raz()
	sens=1

	# Ajoute le 1er alien, le nombre maximum est fixé à 15. Cela est du à ma
	# méthode de gestion anti chevauchement. 15 aliens * 32 de largeur = 480 px
	# Add the first alien , the max number of the aliens is set to 15. It's due
	# at my method to set the intersection between them :
	# 15 aliens * 32 in width = 480 px
	#
	jeu.ajoute_alien(0,15)

	bg=Bg()
	bg = pygame.sprite.RenderPlain((bg))
	
	bandeau=Bandeau()
	allinfo=pygame.sprite.RenderPlain(bandeau)

	# Boucle Jeu / Game loop

	while(jeu.vie>0):

		jeu.clock.tick(FPS)
		jeu.clock_shield.tick(FPS)
		jeu.tick_power()
		keyboard()
		if len(jeu.allalien)!=0:

			# Background
			
			if jeu.optionScroll==0:
				bg.update()
				bg.draw(jeu.surface)
			else:
				jeu.surface.fill(mycolors.BLACK)
				jeu.allpolygon.update()
				jeu.allpolygon.draw(jeu.surface)
		
			# Vaisseau / ship
			
			jeu.surface.blit(vaisseau.image,vaisseau.rect)
			jeu.allgun.update()
			jeu.allgun.draw(jeu.surface)

			# Gestion des aliens / alien

			jeu.allalien.update()
			jeu.allalien.draw(jeu.surface)

			# Mouvement des tirs Aliens / bomb of the Aliens
			
			jeu.allbombealien.update()
			jeu.allbombealien.draw(jeu.surface)

			# Mouvements TIR du vaisseau / fire of the ship

			jeu.allmunition.update()
			jeu.allmunition.draw(jeu.surface)
			jeu.allmunition2.update()
			jeu.allmunition2.draw(jeu.surface)

			# Gestion des cadeaux / surprises
			
			jeu.allcadeau.update()
			jeu.allcadeau.draw(jeu.surface)

			# Display informations
			
			allinfo.update()
			allinfo.draw(jeu.surface)
		
			# Move Nepomuk if exist
			try:
				jeu.nepomuk.update()
			except:
				pass

			pygame.display.flip()


		elif len(jeu.allalien)==0 and jeu.nb_alien<jeu.nb_alien_max:
			
			# Il n'y a plus d'Aliens mais nombre alien max est non atteint...
			# there is no alien to kill but the last level is not reached

			jeu.ajoute_alien(jeu.nb_alien,jeu.nb_alien_max)


			# Plus d'alien mais dernier niveau non atteint
			# No alien to kill but the last level is not reached
			
		elif jeu.niveau<13 :
			
			jeu.nb_alien=0

			####################################################################
			# BOSS LEVEL
			####################################################################

			jeu.empty()
			vaisseau.raz()
			fin=False
			'''
			jeu.niveau=8
			vaisseau.power=100
			'''

			if jeu.niveau<4:
				nb_boss=1
			elif jeu.niveau<8:
				nb_boss=2
			else:
				nb_boss=3

			for i in range(nb_boss):
				boss=Boss()
			while len(jeu.allboss)!=0 and jeu.vie>0:
				
				jeu.clock.tick(FPS)
				keyboard()
				
				if jeu.optionScroll==0:
					bg.update()
					bg.draw(jeu.surface)
				else:
					jeu.surface.fill(mycolors.BLACK)
					jeu.allpolygon.update()
					jeu.allpolygon.draw(jeu.surface)
		
				# Vaisseau / ship
				
				jeu.surface.blit(vaisseau.image,vaisseau.rect)
				jeu.allgun.update()
				jeu.allgun.draw(jeu.surface)

				# Mouvements TIR du vaisseau / fire of the ship
				
				jeu.allmunition.update()
				jeu.allmunition.draw(jeu.surface)
				jeu.allmunition2.update()
				jeu.allmunition2.draw(jeu.surface)


				# Mouvement des tirs aliens
				# Movement of the bombs's Boss
				
				jeu.allbombealien.update()
				jeu.allbombealien.draw(jeu.surface)

				#jeu.bandeau()
				allinfo.update()
				allinfo.draw(jeu.surface)

				# Boss move
				
				jeu.allboss.update()
				jeu.allboss.draw(jeu.surface)

				test_bomb()

				pygame.display.update()

			boss = None

			jeu.raz()
			if jeu.vie!=0:
				jeu.niveau+=1
				if jeu.niveau/4.0==int(jeu.niveau/4.0):
					jeu.vie+=1

			# Dernier niveau Atteint
			# Last level is reached, so go to level 1 and loop
			# Space Max is stronger than you
			
		else:
			jeu.nb_alien=0
			jeu.niveau=1

	jeu.empty()
	jeu.highscore_write()
	jeu.dommage()
	jeu.__init__()

# That's All Folks
# END
