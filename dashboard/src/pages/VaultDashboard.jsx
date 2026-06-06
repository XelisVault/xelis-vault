import React, { useState } from 'react';
import { TrendingUp, Lock, Plus, ArrowRight, Eye, EyeOff } from 'lucide-react';
import './VaultDashboard.css';

export default function VaultDashboard() {
  const [showBalances, setShowBalances] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');

  const vaults = [
    { id: 1, collateral: 10.5, borrowed: 4.2, health: 87, status: 'healthy' },
    { id: 2, collateral: 25.0, borrowed: 10.5, health: 72, status: 'healthy' },
    { id: 3, collateral: 5.0, borrowed: 2.0, health: 65, status: 'warning' },
  ];

  return (
    <div className="vault-dashboard">
      <div className="dashboard-header">
        <div className="header-content">
          <h1>Your Vaults</h1>
          <p>Manage your encrypted positions and collateral</p>
        </div>
        <button className="btn-create-vault">
          <Plus size={20} />
          Create New Vault
        </button>
      </div>

      {/* Overview Stats */}
      <div className="dashboard-stats">
        <div className="stat-card">
          <div className="stat-icon">💰</div>
          <div className="stat-info">
            <div className="stat-label">Total Collateral</div>
            <div className="stat-value">
              {showBalances ? '40.5 XEL' : '●●●●●●●'}
            </div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">💳</div>
          <div className="stat-info">
            <div className="stat-label">Total Borrowed</div>
            <div className="stat-value">
              {showBalances ? '16.7 xUSD' : '●●●●●●●'}
            </div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">📊</div>
          <div className="stat-info">
            <div className="stat-label">Portfolio Health</div>
            <div className="stat-value">
              {showBalances ? '75%' : '●●●●●●●'}
            </div>
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-icon">💵</div>
          <div className="stat-info">
            <div className="stat-label">xUSD Balance</div>
            <div className="stat-value">
              {showBalances ? '8.3 xUSD' : '●●●●●●●'}
            </div>
          </div>
        </div>
      </div>

      {/* Toggle Privacy */}
      <div className="privacy-toggle">
        <button onClick={() => setShowBalances(!showBalances)} className="toggle-btn">
          {showBalances ? <EyeOff size={20} /> : <Eye size={20} />}
          {showBalances ? 'Hide Balances' : 'Show Balances'}
        </button>
      </div>

      {/* Tabs */}
      <div className="dashboard-tabs">
        <button
          className={`tab ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
        >
          Your Vaults
        </button>
        <button
          className={`tab ${activeTab === 'activity' ? 'active' : ''}`}
          onClick={() => setActiveTab('activity')}
        >
          Activity
        </button>
        <button
          className={`tab ${activeTab === 'transactions' ? 'active' : ''}`}
          onClick={() => setActiveTab('transactions')}
        >
          Transactions
        </button>
      </div>

      {/* Vaults Grid */}
      {activeTab === 'overview' && (
        <div className="vaults-grid">
          {vaults.map((vault) => (
            <div key={vault.id} className="vault-card">
              <div className="vault-header">
                <h3>Vault #{vault.id}</h3>
                <div className={`status-badge ${vault.status}`}>
                  {vault.status === 'healthy' ? '✓ Healthy' : '⚠ Warning'}
                </div>
              </div>

              <div className="vault-body">
                <div className="vault-stat">
                  <div className="vault-label">Collateral</div>
                  <div className="vault-value">
                    {showBalances ? `${vault.collateral.toFixed(2)} XEL` : '●●●●●●●'}
                  </div>
                </div>
                <div className="vault-stat">
                  <div className="vault-label">Borrowed</div>
                  <div className="vault-value">
                    {showBalances ? `${vault.borrowed.toFixed(2)} xUSD` : '●●●●●●●'}
                  </div>
                </div>
              </div>

              <div className="vault-health">
                <div className="health-label">Health Factor</div>
                <div className="health-bar">
                  <div
                    className="health-fill"
                    style={{
                      width: `${Math.min(vault.health, 100)}%`,
                      background: vault.health > 70
                        ? 'linear-gradient(90deg, #10b981, #06b6d4)'
                        : vault.health > 50
                        ? 'linear-gradient(90deg, #f59e0b, #ef4444)'
                        : 'linear-gradient(90deg, #ef4444, #dc2626)'
                    }}
                  ></div>
                </div>
                <div className="health-value">{showBalances ? `${vault.health}%` : '●●'}</div>
              </div>

              <div className="vault-actions">
                <button className="action-btn secondary">Repay</button>
                <button className="action-btn primary">Borrow More</button>
              </div>
            </div>
          ))}

          {/* Create New Card */}
          <div className="vault-card create-new">
            <div className="create-content">
              <Plus size={48} />
              <h3>Create New Vault</h3>
              <p>Start a new encrypted position</p>
            </div>
          </div>
        </div>
      )}

      {/* Activity Tab */}
      {activeTab === 'activity' && (
        <div className="activity-section">
          <div className="activity-list">
            {[
              { type: 'deposit', vault: 'Vault #1', amount: 5, time: '2 hours ago' },
              { type: 'borrow', vault: 'Vault #2', amount: 3.5, time: '1 day ago' },
              { type: 'repay', vault: 'Vault #1', amount: 2, time: '3 days ago' },
              { type: 'withdraw', vault: 'Vault #3', amount: 2.5, time: '5 days ago' },
            ].map((activity, idx) => (
              <div key={idx} className="activity-item">
                <div className="activity-icon">
                  {activity.type === 'deposit' && '📥'}
                  {activity.type === 'borrow' && '💳'}
                  {activity.type === 'repay' && '✅'}
                  {activity.type === 'withdraw' && '📤'}
                </div>
                <div className="activity-info">
                  <div className="activity-action">
                    {activity.type === 'deposit' && 'Deposited'}
                    {activity.type === 'borrow' && 'Borrowed'}
                    {activity.type === 'repay' && 'Repaid'}
                    {activity.type === 'withdraw' && 'Withdrew'}
                    {' '}
                    <span className="activity-vault">{activity.vault}</span>
                  </div>
                  <div className="activity-time">{activity.time}</div>
                </div>
                <div className="activity-amount">
                  {activity.type === 'borrow' || activity.type === 'repay'
                    ? `${activity.amount} xUSD`
                    : `${activity.amount} XEL`}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Transactions Tab */}
      {activeTab === 'transactions' && (
        <div className="transactions-section">
          <div className="transaction-list">
            {[
              { hash: '0x7f3a...9c2d', type: 'Deposit', status: 'confirmed', time: '2 hours ago' },
              { hash: '0x2b1e...5a8f', type: 'Borrow', status: 'confirmed', time: '1 day ago' },
              { hash: '0x9d4c...1e3b', type: 'Repay', status: 'confirmed', time: '3 days ago' },
            ].map((tx, idx) => (
              <div key={idx} className="transaction-item">
                <div className="tx-left">
                  <div className="tx-hash">{tx.hash}</div>
                  <div className="tx-type">{tx.type}</div>
                </div>
                <div className="tx-right">
                  <div className={`tx-status ${tx.status}`}>
                    ✓ {tx.status.charAt(0).toUpperCase() + tx.status.slice(1)}
                  </div>
                  <div className="tx-time">{tx.time}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
