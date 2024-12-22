import logging

class YTDLPLogger:
    def __init__(self):
        self.logger = logging.getLogger('yt-dlp')
    
    def debug(self, msg):
        if msg.startswith('[debug] '):
            self.logger.debug(msg[7:])
        else:
            self.logger.debug(msg)
    
    def info(self, msg):
        if msg.startswith('[info] '):
            self.logger.info(msg[6:])
        else:
            self.logger.info(msg)
    
    def warning(self, msg):
        if msg.startswith('[warning] '):
            self.logger.warning(msg[9:])
        else:
            self.logger.warning(msg)
    
    def error(self, msg):
        if msg.startswith('[error] '):
            self.logger.error(msg[7:])
        else:
            self.logger.error(msg) 