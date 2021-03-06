import argparse
import os
import chainer
from chainer import training, optimizers
from chainer.training import extensions

from inpaint_model import InpaintCAModel
from updater import CAUpdater as Updater
from config import Config
from dataset import Dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', type=str, default='',
                        help='path to the snapshot')
    args = parser.parse_args()

    config = Config('contextual_attention.yml')

    # training data
    train_dataset = Dataset(config)
    test_dataset = Dataset(config, test=True)
    train_iter = chainer.iterators.MultiprocessIterator(
        train_dataset, config.BATCH_SIZE)
    test_iter = chainer.iterators.SerialIterator(test_dataset, 8)

    inpaint_model = InpaintCAModel(config)
    if config.GPU_ID >= 0:
        chainer.cuda.get_device(config.GPU_ID).use()
        inpaint_model.to_gpu()

    if not os.path.exists(config.EVAL_FOLDER):
        os.makedirs(config.EVAL_FOLDER)

    # optimizer
    optimizer = {"g_opt": optimizers.Adam(config.ALPHA, config.BETA1, config.BETA2),
                 "d_opt": optimizers.Adam(config.ALPHA, config.BETA1, config.BETA2)}
    optimizer["g_opt"].setup(inpaint_model.inpaintnet)
    optimizer["d_opt"].setup(inpaint_model.discriminator)

    # Set up a trainer
    updater = Updater(
        model=inpaint_model,
        iterator={
            'main': train_iter,
            'test': test_iter
        },
        optimizer=optimizer,
        device=config.GPU_ID,
        config=config,
    )

    trainer = training.Trainer(updater, (config.MAX_ITERS, 'iteration'),
                               out=config.MODEL_RESTORE)
    trainer.extend(extensions.snapshot_object(
        inpaint_model, 'inpaint_model_{.updater.iteration}.npz'), trigger=(config.SNAPSHOT_INTERVAL, 'iteration'))

    log_keys = ['epoch', 'iteration', 'l1_loss', 'ae_loss', 'g_loss', 'd_loss']
    trainer.extend(extensions.LogReport(keys=log_keys, trigger=(20, 'iteration')))
    trainer.extend(extensions.PrintReport(log_keys), trigger=(20, 'iteration'))
    trainer.extend(extensions.ProgressBar(update_interval=50))

    trainer.extend(
        inpaint_model.evaluation(config.EVAL_FOLDER),
        trigger=(config.VAL_PSTEPS, 'iteration')
    )

    if args.snapshot:
        if os.path.exists(args.snapshot):
            print("Resume with snapshot:{}".format(args.snapshot))
            chainer.serializers.load_npz(args.snapshot, inpaint_model)
        else:
            print("{}: invalid snapshot path".format(args.snapshot))

    # Run the training
    trainer.run()


if __name__ == '__main__':
    main()
