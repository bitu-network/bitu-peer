// file: src/web/external/app.js
// filename: /src/www/app.js

const messageBox =
    document.getElementById("message");

const signButton =
    document.getElementById("signButton");

const status =
    document.getElementById("status");


function createLoginMessage() {

    const now =
        new Date()
            .toISOString()
            .replace("T", " ")
            .replace("Z", " UTC");

    return (
        "I want to login to bitu-network.com at "
        + now
    );

}


const loginMessage =
    createLoginMessage();


messageBox.textContent =
    loginMessage;


signButton.onclick = function () {

    status.textContent =
        "Waiting for wallet signature...";

};