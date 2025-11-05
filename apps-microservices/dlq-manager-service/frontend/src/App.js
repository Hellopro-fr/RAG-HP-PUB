import React, { useState } from 'react';
import Dashboard from './components/Dashboard';
import SearchPage from './components/SearchPage';

function App() {
    const [activeTab, setActiveTab] = useState('dashboard');

    const NavButton = ({ tabName, children }) => (
        <button
            onClick={() => setActiveTab(tabName)}
            className={`px-3 py-2 text-sm font-medium rounded-md transition-colors duration-200 ${
                activeTab === tabName
                    ? 'bg-bleu-light text-bleu-primary'
                    : 'text-gris-primary hover:bg-clair-3 hover:text-noir-primary'
            }`}
        >
            {children}
        </button>
    );

    return (
        <div className="bg-white-light min-h-screen font-sans">
            <header className="bg-white-primary shadow-sm sticky top-0 z-40">
                <div className="container mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex items-center justify-between h-16">
                        <h1 className="text-2xl font-bold text-bleu-primary">DLQ Manager</h1>
                        <nav className="flex items-center space-x-2 bg-clair-3 p-1 rounded-lg">
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