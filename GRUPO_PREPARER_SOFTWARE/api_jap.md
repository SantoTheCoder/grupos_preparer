API KEY:
d8226d3452cff23a39636899e8e3e48b

ID DO PEDIDO :
8092

quantidade , 10k por grupo 

API DETAILS
API URL
https://justanotherpanel.com/api/v2

API Key (can be found in your account page)
Your API Key
HTTP Method
POST
Response format
JSON
Example Code
https://justanotherpanel.com/example.txt
Service list
key
Your API key
action
services
[
    {
        "service": 1,
        "name": "Followers",
        "type": "Default",
        "category": "First Category",
        "rate": "0.90",
        "min": "50",
        "max": "10000",
        "refill": true,
        "cancel": true
    },
    {
        "service": 2,
        "name": "Comments",
        "type": "Custom Comments",
        "category": "Second Category",
        "rate": "8",
        "min": "10",
        "max": "1500",
        "refill": false,
        "cancel": true
    }
]
Add order

Default
key
Your API key
action
add
service
Service ID
link
Link to page
quantity
Needed quantity
runs (optional)
Runs to deliver
interval (optional)
Interval in minutes
{
    "order": 23501
}
Order status
key
Your API key
action
status
order
Order ID
{
    "charge": "0.27819",
    "start_count": "3572",
    "status": "Partial",
    "remains": "157",
    "currency": "USD"
}
Multiple orders status
key
Your API key
action
status
orders
Order IDs (separated by a comma, up to 100 IDs)
{
    "1": {
        "charge": "0.27819",
        "start_count": "3572",
        "status": "Partial",
        "remains": "157",
        "currency": "USD"
    },
    "10": {
        "error": "Incorrect order ID"
    },
    "100": {
        "charge": "1.44219",
        "start_count": "234",
        "status": "In progress",
        "remains": "10",
        "currency": "USD"
    }
}
Create refill
key
Your API key
action
refill
order
Order ID
{
    "refill": "1"
}
Create multiple refill
key
Your API key
action
refill
orders
Order IDs (separated by a comma, up to 100 IDs)
[
    {
        "order": 1,
        "refill": 1
    },
    {
        "order": 2,
        "refill": 2
    },
    {
        "order": 3,
        "refill": {
            "error": "Incorrect order ID"
        }
    }
]
Get refill status
key
Your API key
action
refill_status
refill
Refill ID
{
    "status": "Completed"
}
Get multiple refill status
key
Your API key
action
refill_status
refills
Refill IDs (separated by a comma, up to 100 IDs)
[
    {
        "refill": 1,
        "status": "Completed"
    },
    {
        "refill": 2,
        "status": "Rejected"
    },
    {
        "refill": 3,
        "status": {
            "error": "Refill not found"
        }
    }
]
Create cancel
key
Your API key
action
cancel
orders
Order IDs (separated by a comma, up to 100 IDs)
[
    {
        "order": 9,
        "cancel": {
            "error": "Incorrect order ID"
        }
    },
    {
        "order": 2,
        "cancel": 1
    }
]
User balance
key
Your API key
action
balance
{
    "balance": "100.84292",
    "currency": "USD"
}