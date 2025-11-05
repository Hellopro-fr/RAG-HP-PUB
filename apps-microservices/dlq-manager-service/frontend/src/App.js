import React, { useState } from 'react';
import Dashboard from './components/Dashboard';
import SearchPage from './components/SearchPage';
import './App.css';

function App() {
    const [activeTab, setActiveTab] = useState('dashboard');

    const NavButton = ({ tabName, children }) => (
        <button
            onClick={() => setActiveTab(tabName)}
            className={`px-4 py-2 text-sm font-medium transition-colors duration-200 ${
                activeTab === tabName
                    ? 'text-orange-primary border-b-2 border-orange-primary'
                    : 'text-gris-clair hover:text-white-primary'
            }`}
        >
            {children}
        </button>
    );

    return (
        <div className="bg-bleu-noir-2 text-clair-3 min-h-screen font-sans">
            <header className="bg-bleu-noir shadow-md">
                <div className="container mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        <h1 className="text-2xl font-bold text-orange-primary">DLQ Manager</h1>
                        <nav className="flex space-x-4">
                            <NavButton tabName="dashboard">Dashboard</NavButton>
                            <NavButton tabName="search">Search & Re-queue</NavButton>
                        </nav>
                    </div>
                </div>
            </header>
            <main className="container mx-auto p-4 sm:p-6 lg:p-8">
                {activeTab === 'dashboard' && <Dashboard />}
                {activeTab === 'search' && <SearchPage />}
            </main>
        </div>
    );
}

export default App;