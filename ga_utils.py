import argparse
from apiclient.discovery import build
import httplib2
from oauth2client import client
from oauth2client import file
from oauth2client import tools
import matplotlib.pyplot as plt
import matplotlib
import pandas as pd
import configparser
import os
import re
import utils as u

config = configparser.ConfigParser()
config.read('config.ini')

dir_path = os.path.dirname(os.path.realpath(__file__))

SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']
DISCOVERY_URI = ('https://analyticsreporting.googleapis.com/$discovery/rest')
CLIENT_SECRETS_PATH = dir_path+'/'+str(config['Creds']['CLIENT_SECRETS_PATH'])
VIEW_ID = config['Creds']['VIEW_ID']

class AnalyticsData:
    """ Main class to interact with data """
    def __init__(self, start_date, end_date, dimension, metric, goal, version, analytics='', filter_data=''):
        self.start_date = start_date
        self.end_date = end_date
        self.dimension = dimension
        self.metric = metric
        self.goal = goal
        self.version = version
        self.filter_data = filter_data
        self.analytics = self.setup_auth()
        self.setup_plot()
        u.setup()

    def setup_plot(self):
        """Setup size and style of graphs."""
        fig_size = plt.rcParams['figure.figsize']
        fig_size[0] = 12
        fig_size[1] = 12
        plt.rcParams['figure.figsize'] = fig_size
        plt.style.use('ggplot')

    def setup_auth(self):
        """ Setup Google Analytics Auth"""
        parser = argparse.ArgumentParser(
            formatter_class=argparse.RawDescriptionHelpFormatter,
            parents=[tools.argparser])
        flags = parser.parse_args([])

        flow = client.flow_from_clientsecrets(
            CLIENT_SECRETS_PATH, scope=SCOPES,
            message=tools.message_if_missing(CLIENT_SECRETS_PATH))

        storage = file.Storage('analyticsreporting.dat')
        credentials = storage.get()
        if credentials is None or credentials.invalid:
            credentials = tools.run_flow(flow, storage, flags)
        http = credentials.authorize(http=httplib2.Http())

        analytics = build('analytics', 'v4', http=http, discoveryServiceUrl=DISCOVERY_URI)

        return analytics

    def get_report(self):
        """ Raw request to Google Analytics """
        metric = self.metric + "," + self.goal
        return self.analytics.reports().batchGet(
            body={
                'reportRequests': [
                    {
                        'viewId': VIEW_ID,
                        'dateRanges': [{'startDate': str(self.start_date), 'endDate': self.end_date}],
                        'metrics': [{'expression': "ga:"+d} for d in metric.split(',')],
                        'dimensions': [ {'name': "ga:"+d} for d in self.dimension.split(',')],
                        'filtersExpression': self.filter_data
                    }
                ]
            }
        ).execute()

    def ga_to_df(self,v4_response):
        """ Take a json response from Google Analytics API and transform it to pandas DF"""
        try:
            rows = v4_response['reports'][0]['data']['rows']
            header = v4_response['reports'][0]['columnHeader']
            index_col = header['dimensions']
            _ = index_col.extend([v.get('name') for v in header['metricHeader']['metricHeaderEntries']])
            index_col = [re.sub(r'ga:(.*)', r'\1', v) for v in index_col]
            _dims = [v.get('dimensions') for v in rows]
            _mets = [v.get('metrics')[0].get('values') for v in rows]
            _ = [u.extend(v) for u, v in zip(_dims, _mets)]
            return pd.DataFrame(_dims, columns=index_col)
        except KeyError:
            return pd.DataFrame({'error':pd.Series(['no data for this query'])})

    def get_full_data(self):
        """ Main function retreiving and cleaning data """
        response = self.get_report()
        df = self.ga_to_df(response)
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        for i in (self.metric.split(',')+self.goal.split(',')):
            df[i] = df[i].astype(float)
        return df

    def ts(self, df, title='ts', filter_dim='', filter_val='', ylim=()):
        """ Time series line chart """
        df = self.filter_d(df, filter_dim, filter_val)
        ts_versions = df.groupby(["date", self.version]).sum()
        ts_versions['CR'] = ts_versions[self.goal] / ts_versions[self.metric] * 100
        ts = ts_versions.reset_index().pivot(index='date', columns=self.version, values='CR')
        ts_plot = ts.plot(title=title).legend(loc='center left', bbox_to_anchor=(1, 0.5)) if not ylim else ts.plot(title=title, ylim=ylim).legend(loc='center left', bbox_to_anchor=(1, 0.5))
        plt.savefig(u.dir()+'/ts_versions', bbox_inches = 'tight')
        return ts_plot

    def bar(self,df, filter_dim='', filter_val='', title='bar_versions'):
        """ Barchart line chart """
        df = self.filter_d(df, filter_dim, filter_val)
        df = df.groupby(by=[self.version]).sum()
        df['CR'] = df[self.goal] / df[self.metric] * 100
        bar_plot = self.bar_annotate(df['CR'].sort_values(ascending=False).plot.bar(title=title))
        plt.savefig(u.dir()+'/bar_versions', bbox_inches = 'tight')
        return bar_plot

    def diff(self,df, ref_dim, filter_dim='', filter_val='', title='diff_v'):
        """ Compare 1 dimension value to the rest """
        df = self.filter_d(df, filter_dim, filter_val)
        df = df.groupby(by=[self.version]).sum()
        df['CR'] = df[self.goal] / df[self.metric]
        against_dim = df.reset_index()[df.reset_index()[self.version] == ref_dim]['CR'].iloc[0]
        uplift = ((df['CR'] / against_dim - 1) * 100).sort_values(ascending=False)
        bar_plot = self.bar_annotate(uplift.plot.bar(title=title))
        plt.savefig(u.dir()+'/diff_v', bbox_inches = 'tight')

    def cumulative(self,df, filter_dim='', filter_val='', title='cumulative', ylim=()):
        """ Cumulative line chart that calculate Conversion rate """
        df = self.filter_d(df, filter_dim, filter_val)
        df = df.groupby(['date', self.version]).sum()
        df_metric = df.reset_index().pivot(index='date',columns=self.version, values=self.metric).cumsum()
        df_goal = df.reset_index().pivot(index='date',columns=self.version, values=self.goal).cumsum()
        df_cr = df_metric / df_goal * 100
        df_cr.reset_index().plot(title=title).legend(loc='center left', bbox_to_anchor=(1, 0.5)) if not ylim else df_cr.reset_index().plot(title=title, ylim=ylim).legend(loc='center left', bbox_to_anchor=(1, 0.5))
        plt.savefig(u.dir()+'/cumulative', bbox_inches = 'tight')

    def diff_cumul(self,df, ref_dim, filter_dim='', filter_val='', title='cumulative_diff',ylim=()):
        """ Compare 1 dimension value to the rest cumulatively with line chart """
        df = self.filter_d(df, filter_dim, filter_val)
        df = df.groupby(['date', self.version]).sum()
        df_metric = df.reset_index().pivot(index='date',columns=self.version, values=self.metric).cumsum()
        df_goal = df.reset_index().pivot(index='date',columns=self.version, values=self.goal).cumsum()
        df_cr = df_metric / df_goal * 100
        df_cr.apply(lambda x: (x / df_cr[ref_dim]-1)*100).plot(title=title).legend(loc='center left', bbox_to_anchor=(1, 0.5)) if not ylim else df_cr.apply(lambda x: (x / df_cr[ref_dim]-1)*100).plot(title=title,ylim=ylim).legend(loc='center left', bbox_to_anchor=(1, 0.5))
        plt.savefig(u.dir()+'/cumulative_diff', bbox_inches = 'tight')

    def bar_annotate(self,ax):
        """ Annotate function for barchart """
        for p in ax.patches:
            b=p.get_bbox()
            ax.annotate("{:+.2f}".format(b.y1 + b.y0), ((b.x0 + b.x1)/2 - 0.03, b.y1 + 0.02))

    def filter_d(self, df, filter_dim='',filter_val=''):
        if filter_dim != '' or filter_val!='':
            df = df[df[filter_dim] == filter_val]
        return df
