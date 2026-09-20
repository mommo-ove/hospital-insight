import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, App as AntApp } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import './styles.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ConfigProvider locale={zhCN} theme={{ token: { colorPrimary: '#17685a', colorInfo: '#17685a', borderRadius: 9, fontFamily: 'Inter, "Microsoft YaHei", "PingFang SC", sans-serif', colorText: '#263732', colorBgLayout: '#f6f8f6' } }}><AntApp><App /></AntApp></ConfigProvider></React.StrictMode>,
);
