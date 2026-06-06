import React from 'react';
import { BookOpen, Lock, Zap, Shield } from 'lucide-react';
import './Documentation.css';

export default function Documentation() {
  return (
    <div className="documentation">
      <div className="doc-header">
        <h1>Documentation</h1>
        <p>Learn how XELIS Vault works and how to use it</p>
      </div>

      <div className="doc-container">
        {/* Navigation */}
        <aside className="doc-nav">
          <div className="nav-section">
            <h3>Getting Started</h3>
            <a href="#what-is-xelis">What is XELIS Vault?</a>
            <a href="#why-privacy">Why Privacy Matters</a>
            <a href="#how-it-works">How It Works</a>
          </div>
          <div className="nav-section">
            <h3>Concepts</h3>
            <a href="#collateral">Collateral & LTV</a>
            <a href="#xusd">xUSD Stablecoin</a>
            <a href="#health">Health Factor</a>
            <a href="#liquidation">Liquidation</a>
          </div>
          <div className="nav-section">
            <h3>Products</h3>
            <a href="#lending">Confidential Lending</a>
            <a href="#marketplace">Marketplace</a>
            <a href="#treasury">Treasury Management</a>
            <a href="#governance">Governance</a>
          </div>
          <div className="nav-section">
            <h3>Security</h3>
            <a href="#privacy">Privacy Model</a>
            <a href="#risks">Risk Management</a>
            <a href="#audit">Audits</a>
          </div>
        </aside>

        {/* Main Content */}
        <main className="doc-content">
          {/* What is XELIS Vault */}
          <section id="what-is-xelis" className="doc-section">
            <h2>What is XELIS Vault?</h2>
            <p>
              XELIS Vault is a decentralized financial platform built on the XELIS BlockDAG. It enables users to:
            </p>
            <ul>
              <li><strong>Borrow</strong> xUSD stablecoin against encrypted XEL collateral</li>
              <li><strong>Lend</strong> liquidity and earn yield on private positions</li>
              <li><strong>Trade</strong> in sealed-bid auctions without front-running</li>
              <li><strong>Manage</strong> treasuries with multi-signature confidentiality</li>
              <li><strong>Tokenize</strong> real-world assets with full privacy</li>
              <li><strong>Govern</strong> the protocol through VLT token holders</li>
            </ul>
            <p>
              All positions, transactions, and balances are <strong>encrypted by default</strong> using XELIS native homomorphic encryption.
            </p>
          </section>

          {/* Why Privacy */}
          <section id="why-privacy" className="doc-section">
            <h2>Why Privacy Matters</h2>
            <div className="privacy-reasons">
              <div className="reason">
                <h4>🛡️ Protection from MEV</h4>
                <p>Front-runners cannot see your transactions before execution, eliminating MEV extraction.</p>
              </div>
              <div className="reason">
                <h4>🏛️ Institutional Access</h4>
                <p>Regulated entities can participate without revealing their positions or strategies.</p>
              </div>
              <div className="reason">
                <h4>👤 Personal Privacy</h4>
                <p>Your financial decisions remain yours. No public record of your holdings or borrowing.</p>
              </div>
              <div className="reason">
                <h4>⚖️ Fair Markets</h4>
                <p>Level playing field. Larger holders don't get targeted by bots.</p>
              </div>
            </div>
          </section>

          {/* How It Works */}
          <section id="how-it-works" className="doc-section">
            <h2>How It Works</h2>
            <div className="process-steps">
              <div className="step">
                <div className="step-number">1</div>
                <div className="step-content">
                  <h4>Deposit Collateral</h4>
                  <p>Lock XEL into VaultEngine. Your balance is encrypted using XELIS Twisted ElGamal.</p>
                </div>
              </div>
              <div className="step">
                <div className="step-number">2</div>
                <div className="step-content">
                  <h4>Borrow xUSD</h4>
                  <p>Borrow up to 50% of your collateral value. Your debt is private.</p>
                </div>
              </div>
              <div className="step">
                <div className="step-number">3</div>
                <div className="step-content">
                  <h4>Use Privately</h4>
                  <p>Spend xUSD, trade on Forge, or send to others. All transfers are encrypted.</p>
                </div>
              </div>
              <div className="step">
                <div className="step-number">4</div>
                <div className="step-content">
                  <h4>Repay & Withdraw</h4>
                  <p>Repay your debt and withdraw collateral. All transactions encrypted end-to-end.</p>
                </div>
              </div>
            </div>
          </section>

          {/* Collateral & LTV */}
          <section id="collateral" className="doc-section">
            <h2>Collateral & LTV</h2>
            <p>
              XELIS Vault is a <strong>overcollateralized lending protocol</strong>. This means your collateral must always be worth more than your debt.
            </p>
            <div className="formula-box">
              <strong>Minimum Collateral Ratio: 150%</strong>
              <p>For every $1 you borrow, you must deposit at least $1.50 of collateral.</p>
              <div className="example">
                <strong>Example:</strong>
                <ul>
                  <li>You deposit 10 XEL worth $300 (at $30/XEL)</li>
                  <li>You can borrow up to: $300 ÷ 1.5 = $200 xUSD</li>
                  <li>Your collateral ratio: 150% (healthy)</li>
                </ul>
              </div>
            </div>
          </section>

          {/* xUSD Stablecoin */}
          <section id="xusd" className="doc-section">
            <h2>xUSD Stablecoin</h2>
            <p>
              xUSD is a confidential stablecoin minted by VaultEngine. It maintains a $1 peg through multiple mechanisms:
            </p>
            <div className="peg-mechanisms">
              <div className="mechanism">
                <h4>1. Redemption (Primary)</h4>
                <p>Anyone can burn xUSD to reclaim collateral at face value. This creates demand when xUSD trades below $1.</p>
              </div>
              <div className="mechanism">
                <h4>2. Arbitrage</h4>
                <p>When xUSD trades above $1, users can borrow at $1 face value and sell for profit, increasing supply.</p>
              </div>
              <div className="mechanism">
                <h4>3. Overcollateralization</h4>
                <p>Every xUSD is backed by at least $1.50 of XEL collateral, creating an inherent floor value.</p>
              </div>
              <div className="mechanism">
                <h4>4. Savings Rate</h4>
                <p>Adjustable yield on xUSD deposits incentivizes holding or spending when needed.</p>
              </div>
            </div>
          </section>

          {/* Health Factor */}
          <section id="health" className="doc-section">
            <h2>Health Factor</h2>
            <p>
              Your Health Factor measures how safe your position is. It's calculated as:
            </p>
            <div className="formula-box">
              <strong>Health Factor = (Collateral Value × 100) / Borrow Value</strong>
              <div className="health-ranges">
                <div className="range good">
                  <strong>&gt; 200%:</strong> Very safe. You have 2x collateral for your debt.
                </div>
                <div className="range warning">
                  <strong>150%-200%:</strong> Healthy. Minimum required ratio maintained.
                </div>
                <div className="range danger">
                  <strong>&lt; 150%:</strong> Liquidation risk. You can be liquidated.
                </div>
              </div>
            </div>
          </section>

          {/* Liquidation */}
          <section id="liquidation" className="doc-section">
            <h2>Liquidation</h2>
            <p>
              If your Health Factor falls below 150%, anyone can liquidate your vault:
            </p>
            <ol>
              <li>The liquidator repays your debt in xUSD</li>
              <li>They receive your collateral minus a 5% penalty</li>
              <li>The 5% penalty is burned, reducing supply</li>
            </ol>
            <p>
              <strong>Example:</strong> If you have 10 XEL worth $300 and owe $210 xUSD, your health factor is 142.8% (liquidatable).
              A liquidator can repay $210 and receive $285 of collateral (9.5 XEL minus 5% penalty).
            </p>
          </section>

          {/* Confidential Lending */}
          <section id="lending" className="doc-section">
            <h2>Confidential Lending</h2>
            <p>
              VaultEngine is XELIS Vault's core lending protocol. Key features:
            </p>
            <ul>
              <li><strong>Private Positions:</strong> Only you see your collateral and debt amounts</li>
              <li><strong>Dynamic Interest Rates:</strong> Rates adjust based on pool utilization</li>
              <li><strong>Flexible Collateral:</strong> Any supported token works as collateral</li>
              <li><strong>MEV-Resistant:</strong> Liquidations don't reveal your position</li>
            </ul>
          </section>

          {/* Marketplace */}
          <section id="marketplace" className="doc-section">
            <h2>Marketplace</h2>
            <p>
              XELIS Vault includes multiple financial market primitives:
            </p>
            <div className="markets-grid">
              <div className="market">
                <h4>Private Lending Market</h4>
                <p>Multi-pool lending with dynamic rates and multiple collateral types.</p>
              </div>
              <div className="market">
                <h4>Peer-to-Peer Loans</h4>
                <p>Direct bilateral loans with custom terms between two parties.</p>
              </div>
              <div className="market">
                <h4>Syndicated Pools</h4>
                <p>Multi-lender credit pools for large borrowing needs.</p>
              </div>
              <div className="market">
                <h4>Sealed Auctions</h4>
                <p>Confidential bidding on assets without front-running.</p>
              </div>
            </div>
          </section>

          {/* Treasury */}
          <section id="treasury" className="doc-section">
            <h2>Treasury Management</h2>
            <p>
              TreasuryVault enables DAOs and institutions to manage assets confidentially:
            </p>
            <ul>
              <li>Multi-signature with configurable thresholds</li>
              <li>Role-based access control (owner, signer, viewer)</li>
              <li>Encrypted balances — only authorized signers see totals</li>
              <li>Budget allocations and spending limits</li>
              <li>Automated vesting and distributions</li>
            </ul>
          </section>

          {/* Governance */}
          <section id="governance" className="doc-section">
            <h2>Governance</h2>
            <p>
              VLT is XELIS Vault's governance token. Holders control:
            </p>
            <ul>
              <li>Collateral ratio requirements</li>
              <li>Liquidation penalties</li>
              <li>Interest rate parameters</li>
              <li>Asset whitelists</li>
              <li>Protocol fees allocation</li>
            </ul>
            <p>
              All parameter changes go through a 48-hour timelock, giving the community time to react to proposals.
            </p>
          </section>

          {/* Privacy Model */}
          <section id="privacy" className="doc-section">
            <h2>Privacy Model</h2>
            <p>
              XELIS Vault uses <strong>Twisted ElGamal homomorphic encryption</strong> for privacy:
            </p>
            <table className="privacy-table">
              <tbody>
                <tr>
                  <td><strong>Collateral Amount</strong></td>
                  <td>Encrypted (Ciphertext)</td>
                  <td>Owner only</td>
                </tr>
                <tr>
                  <td><strong>Debt Amount</strong></td>
                  <td>Encrypted (Ciphertext)</td>
                  <td>Owner only</td>
                </tr>
                <tr>
                  <td><strong>Health Factor</strong></td>
                  <td>Computed (plaintext for VM)</td>
                  <td>ZK verifiable</td>
                </tr>
                <tr>
                  <td><strong>xUSD Balances</strong></td>
                  <td>Encrypted (native)</td>
                  <td>Owner only</td>
                </tr>
                <tr>
                  <td><strong>Liquidations</strong></td>
                  <td>Public (event)</td>
                  <td>Everyone</td>
                </tr>
              </tbody>
            </table>
          </section>

          {/* Risk Management */}
          <section id="risks" className="doc-section">
            <h2>Risk Management</h2>
            <p>
              XELIS Vault includes multiple layers of risk mitigation:
            </p>
            <div className="risks-grid">
              <div className="risk">
                <h4>Oracle Risk</h4>
                <p>Price feeds have a 1-hour timelock and use multiple sources.</p>
              </div>
              <div className="risk">
                <h4>Bad Debt</h4>
                <p>Insurance pool and reserve fund cover cascading liquidations.</p>
              </div>
              <div className="risk">
                <h4>Smart Contract Risk</h4>
                <p>Open-source code, professional audits, and bug bounty program.</p>
              </div>
              <div className="risk">
                <h4>Governance Risk</h4>
                <p>Timelock and guardian veto protect against malicious proposals.</p>
              </div>
            </div>
          </section>

          {/* Audits */}
          <section id="audit" className="doc-section">
            <h2>Audits & Security</h2>
            <p>
              XELIS Vault underwent comprehensive security analysis:
            </p>
            <div className="audit-info">
              <p><strong>24 bugs identified and fixed</strong> before testnet deployment</p>
              <ul>
                <li>7 critical bugs (fixed)</li>
                <li>8 elevated bugs (fixed)</li>
                <li>6 medium bugs (fixed)</li>
                <li>3 minor bugs (fixed)</li>
              </ul>
              <p>
                Professional security audit scheduled before mainnet launch. Bug bounty program coming soon.
              </p>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
