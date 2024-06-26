#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import numpy as np
import os

from datetime import datetime
from dateutil.relativedelta import relativedelta


# In[2]:


import config
from packages import *


# In[5]:


def load_team_flag(directory, ymd_str):

    target_date = datetime.strptime(ymd_str, '%Y-%m-%d')
    files = os.listdir(directory)

    latest_file = None
    latest_date = None

    for file in files:
        if file.startswith('team_flag_') and file.endswith('.csv'):
            file_date_str = file.split('_')[-1].split('.')[0]
            try:
                file_date = datetime.strptime(file_date_str, '%Y-%m-%d')
                # 주어진 날짜 이전이면서 가장 최근 날짜
                if file_date <= target_date:
                    if latest_date is None or file_date > latest_date:
                        latest_date = file_date
                        latest_file = file
            except ValueError:
                # 날짜 형식이 잘못된 파일은 무시
                continue

    # 최신 파일을 불러오기
    if latest_file:
        # 파일 경로를 포함하여 pandas로 읽기
        return pd.read_csv(os.path.join(directory, latest_file)), latest_file
    else:
        print("No suitable file found.")
        return None


# In[10]:


class preprocessor:
    def __init__(self, path_class):
        self.path_class = path_class
        self.raw_path = self.path_class.raw_path
        self.preprocessed_path = self.path_class.preprocessed_path
        self.upload_path = self.path_class.upload_path

        self.ymd = format_date(path_class.ymd)
        self.thismonth, self.lastmonth = get_previous_months(path_class.ymd)

    def load_data(self):
        query_list = ['hq_profit', 'market_size', 'new_hurbs', 'churned_hurbs', 'new_b2bstores', 'churned_b2bstores', 
                      'previous_new_hurbs', 'previous_churned_hurbs', 'previous_new_b2bstores', 'previous_churned_b2bstores']

        for name in query_list:
            file_path = os.path.join(self.raw_path, f'{name}_{self.ymd}.csv')
            if os.path.isfile(file_path):
                setattr(self, name, pd.read_csv(file_path))
            else:
                pass

        self.team_flag, self.team_flag_name = load_team_flag(self.upload_path, self.ymd)

    def team_flag_preprocessing(self):
        use_cls = ['시도', '시군구2', '사업부' , '팀']

        self.team_flag = self.team_flag[use_cls]
        self.team_flag.columns = ['area_depth1', 'area_depth2', 'department', 'team']

        # 시군구 형식 일치
        # 각 데이터프레임에서 고유한 값들을 집합(set)으로 추출
        market_size_set = set(self.market_size['area_depth2'].astype(str).unique())
        team_flag_set = set(self.team_flag['area_depth2'].unique())

        # marketsize_set에만/team_flag_set에만 존재하는 값들
        unique_to_market_size = market_size_set.difference(team_flag_set)
        unique_to_team_flag = team_flag_set.difference(market_size_set)

        # 결과를 저장할 빈 데이터프레임 생성
        expanded_team_flag = pd.DataFrame(columns=self.team_flag.columns)

        # 각 행에 대해 검사하고 필요에 따라 데이터프레임 확장
        for index, row in self.team_flag.iterrows():
            if row['area_depth2'] in unique_to_team_flag:
                matched_districts = [district for district in unique_to_market_size if row['area_depth2'] in district]
                if matched_districts:
                    for district in matched_districts:
                        new_row = row.copy()
                        new_row['area_depth2'] = district
                        expanded_team_flag = expanded_team_flag.append(new_row, ignore_index=True)
                else:
                    # 매칭되는 구가 없다면 원래 행을 그대로 추가
                    expanded_team_flag = expanded_team_flag.append(row, ignore_index=True)
            else:
                # 매칭 대상이 아닌 경우 원래 행을 그대로 추가
                expanded_team_flag = expanded_team_flag.append(row, ignore_index=True)

        # 결과 확인
        replaced_team_flag = expanded_team_flag.replace('세종시', '세종특별자치시')

        # 시도 형식 일치
        # 결과를 저장할 사전
        mapping_dict = {}
        tf = replaced_team_flag['area_depth1'].unique()
        ms = self.market_size['area_depth1'].astype(str).unique()

        # 각 줄임말에 대해 전체 이름을 찾고 매핑
        for short_name in tf:
            for full_name in ms:
                # 줄임말의 모든 글자가 전체 이름에 포함되어 있는지 확인
                if all(char in full_name for char in short_name):
                    mapping_dict[short_name] = full_name
                    
        self.team_flag = replaced_team_flag.replace(mapping_dict).drop_duplicates()

        # 빈값 채우기
        self.team_flag.loc[self.team_flag['area_depth2'] == '세종특별자치시', 'department'] = '중부사업부'
        self.team_flag.loc[self.team_flag['area_depth2'] == '세종특별자치시', 'team'] = '4팀'

        file_path = os.path.join(self.preprocessed_path, f'team_flag_{self.ymd}.csv')
        
        if not os.path.isfile(file_path):
            self.team_flag.to_csv(file_path, index=False)
        else:
            pass
    
    def merge_all(self):

        market_size_sigungu = self.market_size.groupby(['ym', 'area_depth1', 'area_depth2']).sum().reset_index()
        hq_profit_sigunu = self.hq_profit.groupby(['ym', 'area_depth1', 'area_depth2']).sum().reset_index()

        merge1 = pd.merge(market_size_sigungu, hq_profit_sigunu, how='left', on=['ym', 'area_depth1', 'area_depth2']).fillna(0)
        merge2 = pd.merge(merge1, self.team_flag, how='left', on=['area_depth1', 'area_depth2'])

        newhurbs_concat = pd.concat([self.new_hurbs, self.previous_new_hurbs])
        newhurbs_temp = newhurbs_concat[['ym', 'area_depth1', 'area_depth2', 'newhurbs_hq_profit']]
        newhurbs_sigungu = newhurbs_temp.groupby(['ym', 'area_depth1', 'area_depth2'])[['newhurbs_hq_profit']].sum().reset_index()
        
        merge3 = pd.merge(merge2, newhurbs_sigungu, how='left', on=['ym', 'area_depth1', 'area_depth2']).fillna(0)
        
        churnedhurbs_concat = pd.concat([self.churned_hurbs, self.previous_churned_hurbs])
        churnedhurbs_temp = churnedhurbs_concat[['ym', 'area_depth1', 'area_depth2', 'churnedhurbs_hq_profit']]
        churnedhurbs_sigungu = churnedhurbs_temp.groupby(['ym', 'area_depth1', 'area_depth2'])[['churnedhurbs_hq_profit']].sum().reset_index()
        
        merge4 = pd.merge(merge3, churnedhurbs_sigungu, how='left', on=['ym', 'area_depth1', 'area_depth2']).fillna(0)
        
        newb2bstores_concat = pd.concat([self.new_b2bstores, self.previous_new_b2bstores])
        newb2bstores_temp = newb2bstores_concat[['ym', 'area_depth1', 'area_depth2', 'newb2bstores_hq_profit']]
        newb2bstores_sigungu = newb2bstores_temp.groupby(['ym', 'area_depth1', 'area_depth2'])[['newb2bstores_hq_profit']].sum().reset_index()
        
        merge5 = pd.merge(merge4, newb2bstores_sigungu, how='left', on=['ym', 'area_depth1', 'area_depth2']).fillna(0)
        
        churnedb2bstores_concat = pd.concat([self.churned_b2bstores, self.previous_churned_b2bstores])
        churnedb2bstores_temp = churnedb2bstores_concat[['ym', 'area_depth1', 'area_depth2', 'churnedb2bstores_hq_profit']]
        churnedb2bstores_sigungu = churnedb2bstores_temp.groupby(['ym', 'area_depth1', 'area_depth2'])[['churnedb2bstores_hq_profit']].sum().reset_index()
        
        merge6 = pd.merge(merge5, churnedb2bstores_sigungu, how='left', on=['ym', 'area_depth1', 'area_depth2']).fillna(0)

        merge6['barogo_cnt'] = merge6['br_cnt_roadshop'] + merge6['br_cnt_b2b']
        
        file_path = os.path.join(self.preprocessed_path, f'mergeall_{self.ymd}.csv')
        merge6.to_csv(file_path, index=False)
    
    def __call__(self):   
        self.load_data()
        self.team_flag_preprocessing()
        self.merge_all()


# In[8]:


# config.py의 path Class
# packages, __init__.py의 Logger를 얻는 함수.
def path_class(ymd):
    file_class = config.path_class(ymd)
    return file_class

# 본 파일(loaddata.py)의 데이터 로드 Class를 선언하고, 실행 함수
def main(file_class):    
    run_class = preprocessor(file_class) #brand는 이 스크립트의 특이 추가 인자
    run_class()    

# 스크립트 실행함수
def run(ymd):
    file_class = path_class(ymd)
    main(file_class)

# input 입력 조작 및 run 함수 실행
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ymd', type=str, default=datetime.now().strftime('%Y%m%d'))
    args, unknown = parser.parse_known_args()
    
    run(args.ymd)

