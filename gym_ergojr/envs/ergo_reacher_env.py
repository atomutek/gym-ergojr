import time
import gym
import numpy as np
from gym import spaces
from tqdm import tqdm

from gym_ergojr.sim.ball import Ball
from gym_ergojr.sim.single_robot import SingleRobot
from gym_ergojr.utils.math import RandomPointInHalfSphere
from gym_ergojr.utils.pybullet import DistanceBetweenObjects


class ErgoReacherEnv(gym.Env):
    def __init__(self, headless=False, simple=False, backlash=False, max_force=1, max_vel=18, goal_halfsphere=False):
        self.simple = simple
        self.backlash = backlash
        self.max_force = max_force
        self.max_vel = max_vel

        self.robot = SingleRobot(debug=not headless, backlash=backlash)
        self.ball = Ball()
        self.rhis = RandomPointInHalfSphere(0.0, 0.0369, 0.0437,
                                            radius=0.2022, height=0.2610,
                                            min_dist=0.1, halfsphere=goal_halfsphere)
        self.goal = None
        self.dist = DistanceBetweenObjects(bodyA=self.robot.id, bodyB=self.ball.id,
                                           linkA=13, linkB=1)
        self.episodes = 0  # used for resetting the sim every so often
        self.restart_every_n_episodes = 1000

        self.metadata = {
            'render.modes': ['human']
        }

        if not simple:
            # observation = 6 joints + 6 velocities + 3 coordinates for target
            self.observation_space = spaces.Box(low=-1, high=1, shape=(6 + 6 + 3,), dtype=np.float32)  #
            # action = 6 joint angles
            self.action_space = spaces.Box(low=-1, high=1, shape=(6,), dtype=np.float32)  #

        else:
            # observation = 4 joints + 4 velocities + 2 coordinates for target
            self.observation_space = spaces.Box(low=-1, high=1, shape=(4 + 4 + 2,), dtype=np.float32)  #
            # action = 4 joint angles
            self.action_space = spaces.Box(low=-1, high=1, shape=(4,), dtype=np.float32)  #

        super().__init__()

    def seed(self, seed=None):
        return [np.random.seed(seed)]

    def step(self, action):
        if self.simple:
            action_ = np.zeros(6, np.float32)
            action_[[1, 2, 4, 5]] = action
            action = action_

        self.robot.act2(action, max_force=self.max_force, max_vel=self.max_vel)
        self.robot.step()

        reward, done = self._getReward()

        obs = self._get_obs()
        return obs, reward, done, {}

    def _getReward(self):
        done = False

        reward = self.dist.query()
        reward *= -1  # the reward is the inverse distance

        if reward > -0.016:  # this is a bit arbitrary, but works well
            done = True
            reward = 1

        return reward, done

    def _setDist(self):
        self.dist.bodyA = self.robot.id
        self.dist.bodyB = self.ball.id

    def reset(self):
        self.episodes += 1
        if self.episodes >= self.restart_every_n_episodes:
            self.robot.hard_reset()  # this always has to go first
            self.ball.hard_reset()
            self._setDist()
            self.episodes = 0

        if self.simple:
            self.goal = self.rhis.sampleSimplePoint()
        else:
            self.goal = self.rhis.samplePoint()
        self.dist.goal = self.goal

        self.ball.changePos(self.goal)
        for _ in range(20):
            self.robot.step()  # we need this to move the ball

        qpos = np.random.uniform(low=-0.2, high=0.2, size=6)

        if self.simple:
            qpos[[0, 3]] = 0

        self.robot.reset()
        self.robot.set(np.hstack((qpos, [0] * 6)))
        self.robot.act2(np.hstack((qpos)))
        self.robot.step()

        return self._get_obs()

    def _get_obs(self):
        obs = np.hstack([
            self.robot.observe(),
            self.rhis.normalize(self.goal)
        ])
        if self.simple:
            obs = obs[[1, 2, 4, 5, 7, 8, 10, 11, 13, 14]]
        return obs

    def render(self, mode='human', close=False):
        pass

    def close(self):
        self.robot.close()

    def _get_state(self):
        return self.robot.observe()

    def _set_state(self, posvel):
        if self.simple:
            new_state = np.zeros((12), dtype=np.float32)
            new_state[[1, 2, 4, 5, 7, 8, 10, 11]] = posvel
        else:
            new_state = np.array(posvel)
        self.robot.set(new_state)


if __name__ == '__main__':
    import gym
    import gym_ergojr
    import time

    # MODE = "manual"
    # env = gym.make("ErgoReacher-Graphical-Simple-v1")

    MODE = "timings"
    env = gym.make("ErgoReacher-Headless-Simple-v1")

    env.reset()

    timings = []
    ep_count = 0

    start = time.time()

    if MODE == "manual":
        r = range(100)
    else:
        r = tqdm(range(10000))

    for _ in r:
        while True:
            action = env.action_space.sample()
            obs, rew, done, misc = env.step(action)

            if MODE == "manual":
                print("act {}, obs {}, rew {}, done {}".format(
                    action,
                    obs,
                    rew,
                    done
                ))
                time.sleep(0.01)

            if MODE == "timings":
                ep_count += 1
                if ep_count >= 10000:
                    diff = time.time() - start
                    print("avg. fps: {}".format(np.around(10000 / diff, 3)))
                    np.savez("timings.npz", time=np.around(10000 / diff, 3))
                    ep_count = 0
                    start = time.time()

            if done:
                env.reset()
                break
