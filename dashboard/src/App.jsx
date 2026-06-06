import React, { useState } from 'react';
import { Menu, X } from 'lucide-react';
import LandingPage from './pages/LandingPage';
import VaultDashboard from './pages/VaultDashboard';
import Documentation from './pages/Documentation';
import './App.css';

export default function App() {
  const [currentPage, setCurrentPage] = useState('landing');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="app">
      {/* Mobile Menu Button */}
      <div className="mobile-menu-button">
        <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)}>
          {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
      </div>

      {/* Mobile Menu */}
      {mobileMenuOpen && (
        <div className="mobile-menu">
          <button onClick={() => { setCurrentPage('landing'); setMobileMenuOpen(false); }}>
            Home
          </button>
          <button onClick={() => { setCurrentPage('docs'); setMobileMenuOpen(false); }}>
            Docs
          </button>
          <button onClick={() => { setCurrentPage('dashboard'); setMobileMenuOpen(false); }}>
            Dashboard
          </button>
        </div>
      )}

      {/* Main Content */}
      {currentPage === 'landing' && <LandingPage />}
      {currentPage === 'docs' && <Documentation />}
      {currentPage === 'dashboard' && <VaultDashboard />}

      {/* Navigation Bar for Desktop */}
      {currentPage !== 'landing' && (
        <div className="navbar-bottom">
          <button onClick={() => setCurrentPage('landing')} className="nav-btn">← Back</button>
        </div>
      )}

      {/* Dashboard CTA in Landing */}
      {currentPage === 'landing' && (
        <div className="floating-cta">
          <button
            className="floating-btn"
            onClick={() => setCurrentPage('dashboard')}
            title="Try Dashboard"
          >
            📊
          </button>
        </div>
      )}
    </div>
  );
}
