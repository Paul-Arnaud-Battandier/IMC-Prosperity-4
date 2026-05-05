# IMC Prosperity 4

This repository is a technical record of participation in the IMC Prosperity 4 challenge. It contains the automated trading bots and quantitative analysis tools developed to navigate the various market phases of the space economy.

## Project Overview

The objective of the project was the creation of algorithmic systems capable of trading diverse assets and thematic groups while managing risk. The systems transitioned from basic market making foundations to advanced statistical arbitrage by utilizing historical data and real time order book dynamics.

## Repository Structure

| Directory | Technical Focus |
| :--- | :--- |
| `tutorial_round/` | Initial exploration of the datamodel and execution flow |
| `round_1/` | Foundation of commodity trading using fundamental price logic |
| `round_2/` | Portfolio management across multiple correlated assets |
| `round_3/` | Identification of hidden market patterns and structural relationships |
| `round_4/` | Refinement of execution logic to handle periods of high volatility |
| `round_5/` | Implementation of multi group lead lag predictors and beta calibration |
| `datamodel.py` | Official IMC Prosperity space datamodel classes |

## Quantitative Methods

*   **Market Making**: Providing liquidity through passive limit orders to capture the bid ask spread.
*   **Lead Lag Prediction**: Identifying timing gaps between thematic clusters where one group predicts the movement of another.
*   **WAP Calibration**: Utilizing Weighted Average Price to estimate fair value based on order book volume imbalances.
*   **Linear Regression**: Calculating beta coefficients to scale entries based on leader momentum.
*   **Inventory Control**: Position management logic to maintain strict limits while returning to neutral states.

## Featured Strategies

### Round 5: Statistical Arbitrage
*   **Asset Pairing**: Focused on the relationship between Translators as leaders and Visors as followers.
*   **Signal Calibration**: Applied a calculated beta of 0.0240 to leader momentum to predict follower movements.
*   **Dynamic Offsets**: Utilized real time learning to calculate price offsets for specific assets like the yellow visor.
*   **Risk Limits**: Maintained strict adherence to the 10 unit position limit across all 50 traded products.

## Technical Stack
*   **Language**: Python 3.11
*   **Analysis**: pandas, numpy, matplotlib
*   **Environment**: Jupyter Notebooks for quantitative research and backtesting
