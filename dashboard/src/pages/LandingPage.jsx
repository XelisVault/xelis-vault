import React from 'react';
import { ArrowRight, Shield, Lock, TrendingUp, Zap, FileText } from 'lucide-react';
import './LandingPage.css';

export default function LandingPage() {
  return (
    <div className="landing-page">
      {/* Header/Navigation */}
      <header className="header">
        <div className="header-container">
          <div className="logo">
            <div className="logo-icon">V</div>
            <span>XELIS Vault</span>
          </div>
          <nav className="nav">
            <a href="#features">Features</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#contracts">Contracts</a>
            <a href="#vision">Vision</a>
            <button className="btn-primary">Launch App</button>
          </nav>
        </div>
      </header>

      {/* Hero Section */}
      <section className="hero">
        <div className="hero-content">
          <h1 className="hero-title">
            <span className="gradient-text">Confidential Finance</span>
            <span className="hero-subtitle">for the Privacy Era</span>
          </h1>
          <p className="hero-description">
            The first complete DeFi protocol where your positions, strategies, and holdings remain encrypted on the blockchain. Borrow, lend, and trade privately on XELIS.
          </p>
          <div className="hero-cta">
            <button className="btn-primary-large">Enter Vault</button>
            <button className="btn-secondary-large">
              Learn More
              <ArrowRight size={20} />
            </button>
          </div>
          <div className="hero-stats">
            <div className="stat">
              <div className="stat-value">20</div>
              <div className="stat-label">Smart Contracts</div>
            </div>
            <div className="stat">
              <div className="stat-value">100%</div>
              <div className="stat-label">Encrypted</div>
            </div>
            <div className="stat">
              <div className="stat-value">Zero</div>
              <div className="stat-label">Data Collection</div>
            </div>
          </div>
        </div>
        <div className="hero-visual">
          <div className="floating-card card-1">
            <div className="card-header">Vault #1</div>
            <div className="card-body">
              <div className="encrypted-value">●●●●●●●</div>
              <div className="value-label">Collateral</div>
            </div>
          </div>
          <div className="floating-card card-2">
            <div className="card-header">xUSD Balance</div>
            <div className="card-body">
              <div className="encrypted-value">●●●●●●●</div>
              <div className="value-label">Private</div>
            </div>
          </div>
          <div className="floating-card card-3">
            <div className="card-header">Health Factor</div>
            <div className="card-body">
              <div className="health-bar">
                <div className="health-fill"></div>
              </div>
              <div className="health-label">Safe</div>
            </div>
          </div>
        </div>
      </section>

      {/* Problem Section */}
      <section className="problem-solution">
        <div className="container">
          <div className="section-header">
            <h2>Why XELIS Vault Matters</h2>
            <p>The problem with traditional DeFi is fundamental: transparency at all costs</p>
          </div>
          <div className="problem-grid">
            <div className="problem-item">
              <div className="problem-icon">👁️</div>
              <h3>Everyone sees everything</h3>
              <p>Your positions, liquidations, and strategies are visible to competitors and bots</p>
            </div>
            <div className="problem-item">
              <div className="problem-icon">⚡</div>
              <h3>MEV destroys fair markets</h3>
              <p>Front-runners extract value before your transaction even executes</p>
            </div>
            <div className="problem-item">
              <div className="problem-icon">🚫</div>
              <h3>Institutions are locked out</h3>
              <p>Regulated entities cannot expose their positions on transparent blockchains</p>
            </div>
            <div className="problem-item">
              <div className="problem-icon">📋</div>
              <h3>Privacy is eroded</h3>
              <p>Your financial history is permanent, public, and permanently traceable</p>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="features">
        <div className="container">
          <div className="section-header">
            <h2>What You Can Do</h2>
            <p>A complete suite of financial primitives, all encrypted by default</p>
          </div>
          <div className="features-grid">
            {[
              {
                icon: <Lock size={28} />,
                title: "Confidential Lending",
                desc: "Deposit collateral and borrow xUSD. Your position is encrypted — no one sees your leverage or strategy."
              },
              {
                icon: <Shield size={28} />,
                title: "Private Treasury",
                desc: "Multi-signature treasuries for DAOs and institutions. Balances and approvals stay encrypted."
              },
              {
                icon: <Zap size={28} />,
                title: "Instant Flash Loans",
                desc: "Uncollateralized borrowing for arbitrage and liquidations, all privately."
              },
              {
                icon: <TrendingUp size={28} />,
                title: "Sealed Auctions",
                desc: "Bid confidentially. No front-running, no sniping, no revelation of winners until settlement."
              },
              {
                icon: <FileText size={28} />,
                title: "RWA Tokenization",
                desc: "Tokenize real assets confidentially. Ownership, transfers, and valuations remain private."
              },
              {
                icon: <Shield size={28} />,
                title: "ZK Compliance",
                desc: "Prove institutional eligibility without exposing your identity or business details."
              }
            ].map((feature, idx) => (
              <div key={idx} className="feature-card">
                <div className="feature-icon">{feature.icon}</div>
                <h3>{feature.title}</h3>
                <p>{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works Section */}
      <section id="how-it-works" className="how-it-works">
        <div className="container">
          <div className="section-header">
            <h2>How It Works</h2>
            <p>The mechanics behind confidential DeFi</p>
          </div>
          <div className="timeline">
            {[
              {
                step: 1,
                title: "Deposit XEL",
                description: "Lock your XEL as collateral. The amount is encrypted using XELIS native Twisted ElGamal.",
                icon: "📥"
              },
              {
                step: 2,
                title: "Borrow xUSD",
                description: "Borrow up to 50% of your collateral value in xUSD. Your debt is private.",
                icon: "💰"
              },
              {
                step: 3,
                title: "Use or Swap",
                description: "Spend xUSD, trade on XELIS Forge DEX, or send privately to others.",
                icon: "🔄"
              },
              {
                step: 4,
                title: "Repay & Withdraw",
                description: "Repay your debt and withdraw collateral. All transactions are encrypted end-to-end.",
                icon: "✅"
              }
            ].map((item, idx) => (
              <div key={idx} className="timeline-item">
                <div className="timeline-marker">
                  <div className="marker-number">{item.icon}</div>
                </div>
                <div className="timeline-content">
                  <h3>{item.title}</h3>
                  <p>{item.description}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Contracts Section */}
      <section id="contracts" className="contracts">
        <div className="container">
          <div className="section-header">
            <h2>20 Smart Contracts</h2>
            <p>A modular, interconnected ecosystem of financial primitives</p>
          </div>
          <div className="contracts-showcase">
            <div className="contract-category">
              <h3>Core Lending</h3>
              <div className="contract-list">
                {['VaultEngine', 'xUSD Stablecoin', 'PriceOracle', 'InterestRateModel', 'FlashLoan', 'SavingsRate'].map((c, i) => (
                  <div key={i} className="contract-badge">{c}</div>
                ))}
              </div>
            </div>
            <div className="contract-category">
              <h3>Markets</h3>
              <div className="contract-list">
                {['LendingMarket', 'PeerLoan', 'SyndicatePool', 'SealedBidAuction'].map((c, i) => (
                  <div key={i} className="contract-badge">{c}</div>
                ))}
              </div>
            </div>
            <div className="contract-category">
              <h3>Governance & Treasury</h3>
              <div className="contract-list">
                {['VLT Token', 'GovernanceVault', 'Timelock', 'TreasuryVault', 'RevenueShare', 'Payroll'].map((c, i) => (
                  <div key={i} className="contract-badge">{c}</div>
                ))}
              </div>
            </div>
            <div className="contract-category">
              <h3>Compliance & Insurance</h3>
              <div className="contract-list">
                {['ComplianceModule', 'InsurancePool', 'PrivateInsurance'].map((c, i) => (
                  <div key={i} className="contract-badge">{c}</div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Vision Section */}
      <section id="vision" className="vision">
        <div className="container">
          <div className="section-header">
            <h2>The Vision</h2>
            <p>Financial privacy is a right, not a privilege</p>
          </div>
          <div className="vision-grid">
            <div className="vision-item">
              <h3>🏦 For Institutions</h3>
              <p>Participate in DeFi while maintaining compliance and confidentiality. Prove eligibility without exposing business details.</p>
            </div>
            <div className="vision-item">
              <h3>🛡️ For Individuals</h3>
              <p>Borrow and lend without surveillance. Your financial decisions belong to you, not to the world.</p>
            </div>
            <div className="vision-item">
              <h3>⚖️ For Markets</h3>
              <p>Fair, MEV-resistant pricing. No front-running. No extraction of value by bots. Just markets that work.</p>
            </div>
            <div className="vision-item">
              <h3>🌍 For the World</h3>
              <p>XELIS Vault is open-source and uncensorable. Build on it, fork it, improve it. Financial privacy for everyone.</p>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-final">
        <div className="container">
          <h2>Ready to Take Control of Your Finances?</h2>
          <p>Join us in building the future of private, fair, institutional-grade DeFi.</p>
          <button className="btn-primary-large">Launch App</button>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div className="container">
          <div className="footer-content">
            <div className="footer-section">
              <h4>XELIS Vault</h4>
              <p>Confidential Finance for the Privacy Era</p>
            </div>
            <div className="footer-section">
              <h4>Documentation</h4>
              <a href="#">Whitepaper</a>
              <a href="#">Architecture</a>
              <a href="#">Roadmap</a>
            </div>
            <div className="footer-section">
              <h4>Community</h4>
              <a href="https://github.com/XelisVault" target="_blank" rel="noopener noreferrer">GitHub</a>
              <a href="#">Discord</a>
              <a href="#">Twitter</a>
            </div>
            <div className="footer-section">
              <h4>Legal</h4>
              <a href="#">Privacy</a>
              <a href="#">Terms</a>
              <a href="#">Security</a>
            </div>
          </div>
          <div className="footer-bottom">
            <p>&copy; 2026 XELIS Vault. All rights reserved. Built on XELIS BlockDAG.</p>
          </div>
        </div>
      </footer>
    </div>
  );
}
