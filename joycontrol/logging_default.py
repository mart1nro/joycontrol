import logging
import datetime


def configure(console_level=logging.DEBUG, file_level=logging.DEBUG, logfile_name=None):
    """
    Configures logging formatting

    :param console_level: log level of console logger
    :param file_level: log lever of file logger
    :param logfile_name: name of logfile
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        "[%(asctime)s] %(name)s %(funcName)s::%(lineno)s %(levelname)s - %(message)s",
        "%H:%M:%S"
    )

    # create console logger
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(console_level)

    root_logger.addHandler(console_handler)

    # create file logger
    if logfile_name is not None:
        today = datetime.datetime.now()
        name_of_file = today.strftime(f'%Y-%m-%d_%H-%M_{logfile_name}.log')

        file_handler = logging.FileHandler(name_of_file)
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)

        root_logger.addHandler(file_handler)


if __name__ == "__main__":
    # Run test output on stdout
    configure()

    logger = logging.getLogger("test")

    def test():
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warning msg")

    def test2():
        logger.error("error msg")
        logger.critical("critical msg")

    # test debug, info, warning
    test()
    # test error, critical
    test2()

    # test exceptions
    try:
        raise RuntimeError("It's a trap!")
    except Exception as e:
        logger.exception(e)
