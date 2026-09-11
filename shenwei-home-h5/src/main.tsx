import React from 'react';
import ReactDOM from 'react-dom/client';
import { Chat } from './pages/Chat';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Chat />
  </React.StrictMode>,
);
