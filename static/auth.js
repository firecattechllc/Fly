"use strict";
let setup=false;
const heading=document.getElementById("authHeading");
const intro=document.getElementById("authIntro");
const password=document.getElementById("password");
const submit=document.getElementById("submit");
const message=document.getElementById("authMessage");
async function init(){
 try {
  const r=await fetch("/api/auth/status",{cache:"no-store"});
  if(!r.ok)throw new Error("Authentication service unavailable");
  const state=await r.json();setup=!state.configured;
  if(state.authenticated){location.replace("/");return}
  if(setup){
   heading.textContent="Create owner password";
   intro.textContent="First-time setup. Choose a unique password of at least 14 characters. Store it in your password manager; no password recovery is currently available.";
   password.autocomplete="new-password";
   submit.firstChild.textContent="CREATE OWNER ACCOUNT ";
  }
 }catch(e){message.textContent=e.message;message.className="form-message err";submit.disabled=true}
}
document.getElementById("authForm").addEventListener("submit",async e=>{
 e.preventDefault();submit.disabled=true;message.textContent="Verifying…";message.className="form-message";
 try{
  const result=await fetch(setup?"/api/auth/setup":"/api/auth/login",{
   method:"POST",headers:{"Content-Type":"application/json"},credentials:"same-origin",
   body:JSON.stringify({password:password.value})
  });
  const data=await result.json();
  if(!result.ok)throw new Error(data.error||"Authentication failed");
  password.value="";location.replace("/");
 }catch(err){message.textContent=err.message;message.className="form-message err";submit.disabled=false}
});
init();
