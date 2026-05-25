export interface VaultConfig {
    daemonUrl: string;
    walletUrl: string;
    vaultContract: string;
    xusdAsset: string;
    oracleContract: string;
    interestContract: string;
    insuranceContract: string;
    flashLoanContract: string;
}

export interface VaultSnapshot {
    id: string;
    owner: string;
    collateralAsset: string;
    collateralPlain: string;
    borrowPlain: string;
    lastUpdateTopo: number;
    liquidated: boolean;
    createdAt: number;
}

export interface UserSummary {
    totalCollateralPlain: string;
    totalBorrowPlain: string;
    vaultCount: number;
    vaultIds: string[];
}

export interface HealthInfo {
    health: number;
    isLiquidatable: boolean;
    collateralValue: string;
    borrowValue: string;
    liquidationPrice: string;
}

export class XelisVaultSDK {
    private config: VaultConfig;

    constructor(config: VaultConfig) {
        this.config = config;
    }

    async getDaemonInfo(): Promise<any> {
        const res = await fetch(`${this.config.daemonUrl}/json_rpc`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: '0',
                method: 'get_info',
                params: {}
            })
        });
        return res.json();
    }

    async callDaemon(method: string, params: any = {}): Promise<any> {
        const res = await fetch(`${this.config.daemonUrl}/json_rpc`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: '0',
                method,
                params
            })
        });
        return res.json();
    }

    async callWallet(method: string, params: any = {}): Promise<any> {
        const res = await fetch(`${this.config.walletUrl}/json_rpc`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                jsonrpc: '2.0',
                id: '0',
                method,
                params
            })
        });
        return res.json();
    }

    async getVault(vaultId: string): Promise<VaultSnapshot | null> {
        const res = await this.callDaemon('get_contract_state', {
            contract: this.config.vaultContract,
            key: `v${vaultId}`
        });
        if (!res.result?.value) return null;
        return res.result.value as VaultSnapshot;
    }

    async getHealth(vaultId: string): Promise<number> {
        const res = await this.callDaemon('contract_call', {
            contract: this.config.vaultContract,
            entry: 'get_health',
            params: [vaultId]
        });
        return res.result?.value?.[0] ?? 0;
    }

    async isLiquidatable(vaultId: string): Promise<boolean> {
        const res = await this.callDaemon('contract_call', {
            contract: this.config.vaultContract,
            entry: 'is_liquidatable',
            params: [vaultId]
        });
        return res.result?.value?.[0] ?? false;
    }

    async getUserSummary(address: string): Promise<UserSummary> {
        const res = await this.callDaemon('get_contract_state', {
            contract: this.config.vaultContract,
            key: 'n'
        });
        const vaultCount = parseInt(res.result?.value ?? '0');
        const vaultIds: string[] = [];
        let totalCollateral = 0n;
        let totalBorrow = 0n;
        for (let i = 0; i < vaultCount; i++) {
            const v = await this.getVault(String(i));
            if (v && v.owner === address && !v.liquidated) {
                vaultIds.push(v.id);
                totalCollateral += BigInt(v.collateralPlain);
                totalBorrow += BigInt(v.borrowPlain);
            }
        }
        return {
            totalCollateralPlain: String(totalCollateral),
            totalBorrowPlain: String(totalBorrow),
            vaultCount: vaultIds.length,
            vaultIds
        };
    }

    async getBorrowRate(totalBorrows: string, totalSupply: string): Promise<number> {
        const res = await this.callDaemon('contract_call', {
            contract: this.config.interestContract,
            entry: 'get_borrow_rate',
            params: [totalBorrows, totalSupply]
        });
        return res.result?.value?.[0] ?? 0;
    }

    async getSupplyRate(totalBorrows: string, totalSupply: string): Promise<number> {
        const res = await this.callDaemon('contract_call', {
            contract: this.config.interestContract,
            entry: 'get_supply_rate',
            params: [totalBorrows, totalSupply]
        });
        return res.result?.value?.[0] ?? 0;
    }

    async getOraclePrice(asset: string): Promise<string> {
        const res = await this.callDaemon('contract_call', {
            contract: this.config.oracleContract,
            entry: 'get_price',
            params: [asset]
        });
        return res.result?.value?.[0] ?? '0';
    }

    async getXusdBalance(address: string): Promise<string> {
        const res = await this.callDaemon('get_balance', {
            address,
            asset: this.config.xusdAsset
        });
        return res.result?.balance ?? '0';
    }

    async getTotalStaked(): Promise<string> {
        const res = await this.callDaemon('contract_call', {
            contract: this.config.insuranceContract,
            entry: 'get_total_staked',
            params: []
        });
        return res.result?.value?.[0] ?? '0';
    }

    async buildHealthInfo(vaultId: string, price: string): Promise<HealthInfo> {
        const vault = await this.getVault(vaultId);
        if (!vault || vault.liquidated) {
            return { health: 0, isLiquidatable: false, collateralValue: '0', borrowValue: '0', liquidationPrice: '0' };
        }
        const collateralVal = (BigInt(vault.collateralPlain) * BigInt(price)) / BigInt(100_000_000);
        const borrowVal = BigInt(vault.borrowPlain);
        const health = borrowVal > 0n ? Number((collateralVal * 100n) / borrowVal) : 999;
        const isLiq = borrowVal > 0n && health < 150;
        const liqPrice = borrowVal > 0n ? String((borrowVal * 150n * 100_000_000n) / BigInt(vault.collateralPlain) / 100n) : '0';

        return {
            health,
            isLiquidatable: isLiq,
            collateralValue: String(collateralVal),
            borrowValue: String(borrowVal),
            liquidationPrice: liqPrice
        };
    }
}
