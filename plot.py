import argparse
import visdom
import torch
from torch.autograd import Variable
from envs.mo_env import MultiObjectiveEnv
import time as Timer
import math
import numpy as np

parser = argparse.ArgumentParser(description='MORL-PLOT')
# CONFIG
parser.add_argument('--env-name', default='dst', metavar='ENVNAME',
				help='environment to train on (default: dst)')
parser.add_argument('--method', default='crl-naive', metavar='METHODS',
				help='methods: crl-naive | crl-envelope | crl-energy')
parser.add_argument('--model', default='linear', metavar='MODELS',
				help='linear | cnn | cnn + lstm')
parser.add_argument('--gamma', type=float, default=0.99, metavar='GAMMA',
				help='gamma for infinite horizonal MDPs')
# PLOT
parser.add_argument('--pltmap', default=False, action='store_true',
				help='plot deep sea treasure map')
parser.add_argument('--pltpareto', default=False, action='store_true',
				help='plot pareto frontier')
parser.add_argument('--pltcontrol', default=False, action='store_true',
				help='plot control curve')
parser.add_argument('--pltdemo', default=False, action='store_true',
				help='plot demo')
# LOG & SAVING
parser.add_argument('--save', default='crl/naive/saved/', metavar='SAVE',
				help='address for saving trained models')
parser.add_argument('--name', default='', metavar='name',
				help='specify a name for saving the model')
# Useless but I am too laze to delete them
parser.add_argument('--mem-size', type=int, default=10000, metavar='M',
				help='max size of the replay memory')
parser.add_argument('--batch-size', type=int, default=256, metavar='B',
				help='batch size')
parser.add_argument('--lr', type=float, default=1e-3, metavar='LR',
				help='learning rate')
parser.add_argument('--epsilon', type=float, default=0.3, metavar='EPS',
				help='epsilon greedy exploration')
parser.add_argument('--epsilon-decay', default=False, action='store_true',
				help='linear epsilon decay to zero')
parser.add_argument('--weight-num', type=int, default=32, metavar='WN',
				help='number of sampled weights per iteration')
parser.add_argument('--episode-num', type=int, default=100, metavar='EN',
				help='number of episodes for training')
parser.add_argument('--optimizer', default='Adam', metavar='OPT',
				help='optimizer: Adam | RMSprop')
parser.add_argument('--update-freq', type=int, default=32, metavar='OPT',
				help='optimizer: Adam | RMSprop')

args = parser.parse_args()

vis = visdom.Visdom()

assert vis.check_connection()

use_cuda = torch.cuda.is_available()
FloatTensor = torch.cuda.FloatTensor if use_cuda else torch.FloatTensor
LongTensor = torch.cuda.LongTensor if use_cuda else torch.LongTensor
ByteTensor = torch.cuda.ByteTensor if use_cuda else torch.ByteTensor
Tensor = FloatTensor

# Add data
gamma    = args.gamma
args 	 = parser.parse_args()	
time	 = [ -1, -3, -5, -7, -8, -9,   -13,	  -14,   -17,   -19]
# treasure = [0.1, 2.8, 5.2, 7.3, 8.2, 9.0, 11.5, 12.1, 13.5, 14.2]
treasure = [0.7, 8.2, 11.5, 14., 15.1, 16.1, 19.6, 20.3, 22.4, 23.7]
# time	 = [ -1, -3, -5, -7, -8, -9]
# treasure = [0.1, 2.8, 5.2, 7.3, 8.2, 9.0]

# apply gamma
dis_time = (-(1 - np.power(gamma, -np.asarray(time))) / (1 - gamma)).tolist()
dis_treasure = (np.power(gamma, -np.asarray(time)-1) * np.asarray(treasure)).tolist()


################# Control Frontier #################

if args.pltcontrol:

	# setup the environment
	env = MultiObjectiveEnv(args.env_name)

	# generate an agent for plotting
	agent = None
	if args.method == 'crl-naive':
		from crl.naive.meta import MetaAgent
	elif args.method == 'crl-envelope':
		from crl.envelope.meta import MetaAgent
	elif args.method == 'crl-energy':
		from crl.energy.meta import MetaAgent
	model = torch.load("{}{}.pkl".format(args.save, args.model+args.name))
	agent = MetaAgent(model, args, is_train=False)

	# compute opt
	opt_x = []
	opt_y = []
	q_x = []
	q_y = []
	act_x = []
	act_y = []
	real_sol = np.stack((dis_treasure, dis_time))

	for i in range(2000):
		w = np.random.randn(2)
		w = np.abs(w) / np.linalg.norm(w, ord=1)
		# w = np.random.dirichlet(np.ones(2))
		w_e = w / np.linalg.norm(w, ord=2)
		if args.method == 'crl-naive' or args.method == 'crl-envelope':
			hq, _ = agent.model(Variable(FloatTensor([0,0]).unsqueeze(0), volatile=True), 
						Variable(torch.from_numpy(w).unsqueeze(0).type(FloatTensor), volatile=True))
		elif args.method == 'crl-energy':
			hq, _ = agent.model(Variable(FloatTensor([0,0]).unsqueeze(0), volatile=True), 
						Variable(torch.from_numpy(w).unsqueeze(0).type(FloatTensor), volatile=True),
						alpha=1e-5)
		realc = w.dot(real_sol).max() * w_e
		qc = w_e
		if args.method == 'crl-naive':
			qc = hq.data[0] * w_e
		elif args.method == 'crl-envelope':
			qc = w.dot(hq.data.cpu().numpy().squeeze()) * w_e
		elif args.method == 'crl-energy':
			qc = w.dot(hq.data.cpu().numpy().squeeze()) * w_e
		ttrw = np.array([0, 0])
		terminal = False
		env.reset()
		cnt = 0
		while not terminal:
			state  = env.observe()
			action = agent.act(state, preference=torch.from_numpy(w).type(FloatTensor))
			next_state, reward, terminal = env.step(action)
			if cnt > 30:
				terminal = True
			ttrw = ttrw + reward * np.power(args.gamma, cnt)
			cnt += 1	
		ttrw_w = w.dot(ttrw) * w_e
		opt_x.append(realc[0])
		opt_y.append(realc[1])
		q_x.append(qc[0])
		q_y.append(qc[1])
		act_x.append(ttrw_w[0])
		act_y.append(ttrw_w[1])


	trace_opt = dict(x=opt_x, 
				 y=opt_y,
				 mode="markers",
				 type='custom',
				 marker = dict(
						symbol="circle",
						size  = 1),
				 name='real')

	q_opt = dict(x=q_x, 
				 y=q_y,
				 mode="markers",
				 type='custom',
				 marker = dict(
						symbol="circle",
						size  = 1),
				 name='predited')

	act_opt = dict(x=act_x, 
				 y=act_y,
				 mode="markers",
				 type='custom',
				 marker = dict(
						symbol="circle",
						size  = 1),
				 name='policy')

	layout_opt=dict(title="DST Control Frontier - {}".format(args.method),
				xaxis=dict(title = 'teasure value'), 
				yaxis=dict(title = 'time penalty'))

	vis._send({'data': [trace_opt, q_opt, act_opt], 'layout': layout_opt})


################# Pareto Frontier #################

if args.pltpareto:


	# setup the environment
	env = MultiObjectiveEnv(args.env_name)

	# generate an agent for plotting
	agent = None
	if args.method == 'crl-naive':
		from crl.naive.meta import MetaAgent
	elif args.method == 'crl-envelope':
		from crl.envelope.meta import MetaAgent
	elif args.method == 'crl-energy':
		from crl.energy.meta import MetaAgent
	model = torch.load("{}{}.pkl".format(args.save, args.model+args.name))
	agent = MetaAgent(model, args, is_train=False)

	# compute recovered Pareto
	act_x = []
	act_y = []

	# predicted solution
	pred_x = []
	pred_y = []

	for i in range(2000):
		w = np.random.randn(2)
		w = np.abs(w) / np.linalg.norm(w, ord=1)
		# w = np.random.dirichlet(np.ones(2))
		ttrw = np.array([0, 0])
		terminal = False
		env.reset()
		cnt = 0
		if args.method == "crl-envelope":
			hq, _ = agent.model(Variable(FloatTensor([0,0]).unsqueeze(0), volatile=True), 
							Variable(torch.from_numpy(w).unsqueeze(0).type(FloatTensor), volatile=True))
			pred_x.append(hq.data.cpu().numpy().squeeze()[0] * 1.0)
			pred_y.append(hq.data.cpu().numpy().squeeze()[1] * 1.0)
		elif args.method == "crl-energy":
			hq, _ = agent.model(Variable(FloatTensor([0,0]).unsqueeze(0), volatile=True), 
							Variable(torch.from_numpy(w).unsqueeze(0).type(FloatTensor), volatile=True),
							alpha=1e-5)
			pred_x.append(hq.data.cpu().numpy().squeeze()[0] * 1.0)
			pred_y.append(hq.data.cpu().numpy().squeeze()[1] * 1.0)
		while not terminal:
			state  = env.observe()
			action = agent.act(state, preference=torch.from_numpy(w).type(FloatTensor))
			next_state, reward, terminal = env.step(action)
			if cnt > 50:
				terminal = True
			ttrw = ttrw + reward * np.power(args.gamma, cnt)
			cnt += 1

		act_x.append(ttrw[0])
		act_y.append(ttrw[1])	

	# Create and style traces
	trace_pareto = dict(x=dis_treasure, 
				 y=dis_time,
				 mode="markers+lines",
				 type='custom',
				 marker=dict(
				 		symbol="circle", 
				 		size  = 10),
				 line = dict(
						width = 1,
						dash  = 'dash'),
				 name='Pareto')

	act_pareto = dict(x=act_x, 
				 y=act_y,
				 mode="markers",
				 type='custom',
				 marker=dict(
				 		symbol="circle", 
				 		size  = 10),
				 line = dict(
						width = 1,
						dash  = 'dash'),
				 name='Recovered')

	pred_pareto = dict(x=pred_x, 
				 y=pred_y,
				 mode="markers",
				 type='custom',
				 marker=dict(
				 		symbol="circle", 
				 		size  = 3),
				 line = dict(
						width = 1,
						dash  = 'dash'),
				 name='Predicted')


	layout=dict(title="DST Pareto Frontier - {}".format(args.method),
				xaxis=dict(   title = 'teasure value',
						   zeroline = False), 
				yaxis=dict(   title = 'time penalty',
						   zeroline = False))

	# send to visdom
	if args.method == "crl-naive":
		vis._send({'data': [trace_pareto, act_pareto], 'layout': layout})
	elif args.method == "crl-envelope":
		vis._send({'data': [trace_pareto, act_pareto, pred_pareto], 'layout': layout})
	elif args.method == "crl-energy":
		vis._send({'data': [trace_pareto, act_pareto, pred_pareto], 'layout': layout})



################# HEATMAP #################

if args.pltmap:
	see_map = np.array(
					[[ 0,   0,   0,   0,   0,   0,    0,    0,    0,    0, 0],
					 [ 0.7,   0,   0,   0,   0,   0,    0,    0,    0,    0, 0],
					 [ -10, 8.2,   0,   0,   0,   0,    0,    0,    0,    0, 0],
					 [ -10, -10,11.5,   0,   0,   0,    0,    0,    0,    0, 0],
					 [ -10, -10, -10,14.0,15.1,16.1,    0,    0,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,    0,    0,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,    0,    0,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10, 19.6, 20.3,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,  -10,  -10,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,  -10,  -10, 22.4,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,  -10,  -10,  -10, 23.7, 0]]
				)[::-1]

	vis.heatmap(X=see_map,
				opts=dict(
					title="DST Map",
					xmin = -10,
					xmax = 16.6))


################# DYNAMICS #################

if args.pltdemo:
	see_map = np.array(
					[[ 0,   0,   0,   0,   0,   0,    0,    0,    0,    0, 0],
					 [ 0.7,   0,   0,   0,   0,   0,    0,    0,    0,    0, 0],
					 [ -10, 8.2,   0,   0,   0,   0,    0,    0,    0,    0, 0],
					 [ -10, -10,11.5,   0,   0,   0,    0,    0,    0,    0, 0],
					 [ -10, -10, -10,14.0,15.1,16.1,    0,    0,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,    0,    0,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,    0,    0,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10, 19.6, 20.3,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,  -10,  -10,    0,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,  -10,  -10, 22.4,    0, 0],
					 [ -10, -10, -10, -10, -10, -10,  -10,  -10,  -10, 23.7, 0]]
				)[::-1]

	# setup the environment
	env = MultiObjectiveEnv(args.env_name)

	# generate an agent for plotting
	agent = None
	if args.method == 'crl-naive':
		from crl.naive.meta import MetaAgent
	elif args.method == 'crl-envelope':
		from crl.envelope.meta import MetaAgent
	elif args.method == 'crl-energy':
		from crl.energy.meta import MetaAgent
	model = torch.load("{}{}.pkl".format(args.save, args.model+args.name))
	agent = MetaAgent(model, args, is_train=False)
	new_episode = True

	while new_episode:

		dy_map = np.copy(see_map)
		dy_map[10 - 0, 0] = -3

		win = vis.heatmap(X=dy_map,
						opts=dict(
							title="DST Map",
							xmin = -10,
							xmax = 16.6))

		w1 = float(raw_input("treasure weight: "))
		w2 = float(raw_input("time weight: "))
		w = np.array([w1, w2])
		w = np.abs(w) / np.linalg.norm(w, ord=1)
		# w = np.random.dirichlet(np.ones(2))
		ttrw = np.array([0, 0])
		terminal = False
		env.reset()
		cnt = 0
		while not terminal:
			state  = env.observe()
			action = agent.act(state, preference=torch.from_numpy(w).type(FloatTensor))
			next_state, reward, terminal = env.step(action)
			dy_map[10 - next_state[0], next_state[1]] = -3
			vis.heatmap(X=dy_map,
						win = win,
						opts=dict(
							title="DST Map",
							xmin = -10,
							xmax = 14.5))
			Timer.sleep(.5)
			if cnt > 50:
				terminal = True
			ttrw = ttrw + reward * np.power(args.gamma, cnt)
			cnt += 1
		print("final reward: treasure %0.2f, time %0.2f, tot %0.2f"%(ttrw[0], ttrw[1], w.dot(ttrw)))
		new_episode = int(raw_input("try again? 1: Yes | 0: No "))