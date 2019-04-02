# MIT License
#
# Copyright (C) IBM Corporation 2018
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
# Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from __future__ import absolute_import, division, print_function, unicode_literals

import logging

import numpy as np

from art.attacks.attack import Attack

logger = logging.getLogger(__name__)


class Boundary(Attack):
    """
    Implementation of the boundary attack from Wieland Brendel et al. (2018).
    Paper link: https://arxiv.org/abs/1712.04248
    """
    attack_params = Attack.attack_params + ['targeted', 'delta', 'epsilon', 'step_adapt', 'max_iter', 'sample_size']

    def __init__(self, classifier, targeted=True, delta=0.01, epsilon=0.01, step_adapt=0.9, max_iter=100,
                 sample_size=20, init_size=100):
        """
        Create a Boundary attack instance.

        :param classifier: A trained model.
        :type classifier: :class:`.Classifier`
        :param targeted: Should the attack target one specific class.
        :type targeted: `bool`
        :param delta: Initial step size for the orthogonal step.
        :type delta: `float`
        :param epsilon: Initial step size for the step towards the target.
        :type epsilon: `float`
        :param step_adapt: Factor by which the step sizes are multiplied or divided, must be in the range (0, 1).
        :type step_adapt: `float`
        :param max_iter: The maximum number of iterations.
        :type max_iter: `int`
        :param sample_size: Maximum number of trials per iteration.
        :type sample_size: `int`
        :param init_size: Maximum number of trials for initial generation of adversarial examples.
        :type init_size: `int`
        """
        super(Boundary, self).__init__(classifier=classifier)
        params = {'targeted': targeted,
                  'delta': delta,
                  'epsilon': epsilon,
                  'step_adapt': step_adapt,
                  'max_iter': max_iter,
                  'sample_size': sample_size,
                  'init_size': init_size}
        self.set_params(**params)

    def generate(self, x, **kwargs):
        """
        Generate adversarial samples and return them in an array.

        :param x: An array with the original inputs to be attacked.
        :type x: `np.ndarray`
        :param y: If `self.targeted` is true, then `y` represents the target labels.
        :type y: `np.ndarray`
        :param targeted: Should the attack target one specific class.
        :type targeted: `bool`
        :param delta: Initial step size for the orthogonal step.
        :type delta: `float`
        :param epsilon: Initial step size for the step towards the target.
        :type epsilon: `float`
        :param step_adapt: Factor by which the step sizes are multiplied or divided, must be in the range (0, 1).
        :type step_adapt: `float`
        :param max_iter: The maximum number of iterations.
        :type max_iter: `int`
        :param sample_size: Maximum number of trials per iteration.
        :type sample_size: `int`
        :param init_size: Maximum number of trials for initial generation of adversarial examples.
        :type init_size: `int`
        :return: An array holding the adversarial examples.
        :rtype: `np.ndarray`
        """
        self.set_params(**kwargs)
        params_cpy = dict(kwargs)
        y = params_cpy.pop(str('y'), None)

        # Prediction from the original images
        preds = np.argmax(self.classifier.predict(x), axis=1)

        # Assert that, if attack is targeted, y is provided
        if self.targeted and y is None:
            raise ValueError('Target labels `y` need to be provided for a targeted attack.')

        # Some initial setups
        x_adv = x.copy()

        # Generate the adversarial samples
        for ind, val in enumerate(x_adv):
            if self.targeted:
                x_ = self._perturb(x=val, y=y[ind], y_p=preds[ind])
            else:
                x_ = self._perturb(x=val, y=None, y_p=preds[ind])

            x_adv[ind] = x_

        preds_adv = np.argmax(self.classifier.predict(x_adv), axis=1)
        logger.info('Success rate of Boundary attack: %.2f%%', (np.sum(preds != preds_adv) / x.shape[0]))

        return x_adv

    def _perturb(self, x, y, y_p):
        """
        Internal attack function for 1 example.

        :param x: An array with 1 original input to be attacked.
        :type x: `np.ndarray`
        :param y: If `self.targeted` is true, then `y` represents the target label.
        :type y: `int`
        :param y_p: The predicted label of x.
        :type y_p: `int`
        :return: an adversarial example.
        """
        clip_min, clip_max = self.classifier.clip_values

        # First, create an initial adversarial sample
        initial_sample = self._init_sample(x, y, y_p, clip_min, clip_max)

        # If an initial adversarial example is not found, then return the original image
        if initial_sample is None:
            return x

        # If an initial adversarial example found, then go with boundary attack
        x_adv = self._attack(initial_sample)

        return x_adv

    def _init_sample(self, x, y, y_p, clip_min, clip_max):
        """
        Find initial adversarial example for the attack.

        :param x: An array with 1 original input to be attacked.
        :type x: `np.ndarray`
        :param y: If `self.targeted` is true, then `y` represents the target label.
        :type y: `int`
        :param y_p: The predicted label of x.
        :type y_p: `int`
        :param clip_min: minimum value of x.
        :type clip_min: `float`
        :param clip_max: maximum value of x.
        :type clip_max: `float`
        :return: an adversarial example.
        """
        nprd = np.random.RandomState()
        initial_sample = None

        if self.targeted:
            # Attack satisfied
            if y == y_p:
                return None

            # Attack unsatisfied yet
            for _ in range(self.init_size):
                random_img = nprd.uniform(clip_min, clip_max, size=x.shape).astype(x.dtype)
                random_class = np.argmax(self.classifier.predict(np.array([random_img])), axis=1)[0]

                if random_class == y:
                    initial_sample = random_img

                    logging.info('Found initial adversarial image for targeted attack.')
                    break
            else:
                logging.warning('Failed to draw a random image that is adversarial, attack failed.')

        else:
            for _ in range(self.init_size):
                random_img = nprd.uniform(clip_min, clip_max, size=x.shape).astype(x.dtype)
                random_class = np.argmax(self.classifier.predict(np.array([random_img])), axis=1)[0]

                if random_class != y_p:
                    initial_sample = random_img

                    logging.info('Found initial adversarial image for untargeted attack.')
                    break
            else:
                logging.warning('Failed to draw a random image that is adversarial, attack failed.')

        return initial_sample

    def set_params(self, **kwargs):
        """
        Take in a dictionary of parameters and applies attack-specific checks before saving them as attributes.

        :param targeted: Should the attack target one specific class.
        :type targeted: `bool`
        :param delta: Initial step size for the orthogonal step.
        :type delta: `float`
        :param epsilon: Initial step size for the step towards the target.
        :type epsilon: `float`
        :param step_adapt: Factor by which the step sizes are multiplied or divided, must be in the range (0, 1).
        :type step_adapt: `float`
        :param max_iter: The maximum number of iterations.
        :type max_iter: `int`
        :param sample_size: Maximum number of trials per iteration.
        :type sample_size: `int`
        :param init_size: Maximum number of trials for initial generation of adversarial examples.
        :type init_size: `int`
        """
        # Save attack-specific parameters
        super(Boundary, self).set_params(**kwargs)

        if not isinstance(self.max_iter, (int, np.int)) or self.max_iter <= 0:
            raise ValueError("The number of iterations must be a positive integer.")

        if not isinstance(self.sample_size, (int, np.int)) or self.sample_size <= 0:
            raise ValueError("The number of trials must be a positive integer.")

        if not isinstance(self.init_size, (int, np.int)) or self.init_size <= 0:
            raise ValueError("The number of trials must be a positive integer.")

        if self.epsilon <= 0:
            raise ValueError("The initial step size for the step towards the target must be positive.")

        if self.delta <= 0:
            raise ValueError("The initial step size for the orthogonal step must be positive.")

        if self.step_adapt <= 0 or self.step_adapt >= 1:
            raise ValueError("The adaptation factor must be in the range (0, 1).")

        return True