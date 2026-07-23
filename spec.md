# Price Tracker
## Goal
I want to track prices over time across various stores for items of interest.  Currently I'm interested in certain lego sets, and a nintendo switch 2 and accessories. I want to have a web dashboard where I can view price trends and receive notifications for price drops.

## Requirements
- Deployable via docker compose for my home server
- Ability to add items to the tracker
- Ability to remove items from the tracker
- Track prices from multiple stores including Target, Best Buy, lego.com, Amazon, Walmart, Woot, and Barnes & Noble.
- Show a graph of price trends over time.
- Price drop notifications - I want to set a threshold for each tracked item and receive a notification if it is found priced below the threshold.  Sending the notifications should not incur cost. They could use email, iOS, alexa, or something else.