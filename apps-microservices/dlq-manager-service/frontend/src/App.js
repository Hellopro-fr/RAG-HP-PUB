import React, { useState } from 'react';
import Dashboard from './components/Dashboard';
import SearchPage from './components/SearchPage';
import './App.css';

function App() {
    const [activeTab, setActiveTab] = useState('dashboard');

    const renderContent = () => {
        switch (activeTab) {
            case 'dashboard':
                return <Dashboard />;
            case 'search':
                return <SearchPage />;
            default:
                return <Dashboard />;
        }
    };

    return (
        <div className="app-container">
            <header className="app-header">
                <h1>DLQ Manager</h1>
                <nav>
                    <button onClick={() => setActiveTab('dashboard')} className={activeTab === 'dashboard' ? 'active' : ''}>Dashboard</button>
                    <button onClick={() => setActiveTab('search')} className={activeTab === 'search' ? 'active' : ''}>Search & Re-queue</button>
                    {/* Functionality #9: Audit Trail can be added here as another tab */}
                </nav>
            </header>
            <main className="app-main">
                {renderContent()}
            </main>
        </div>
    );
}

export default App;