<message id="${msg_id}" from="${filler_exec_1_slack_username}" to="#${channel_exec}" time="${timestamp}">
${ceo_question2}
</message>
<end_of_template>
ceo_question2:
  remote_work: "hey ${ceo_name}, ${employee_2_first_name} is asking about remote work policy - what should I tell them?"
  expense_policy: "hey ${ceo_name} ${exec_first_name} is asking about expense reimbursement. what's the official stance?"
  conference_budget: "${ceo_name} ${employee_1_first_name} is asking about conference budget and I don't actually know what to tell them"
  pay_band_approval: "${employee_2_first_name} wants to extend an offer above pay band. makes sense to me but wanted your approval since it's outside normal limits. details in thread"
  team_travel: "${employee_2_first_name} wants to approve team travel. think it makes sense but wanted your ok since it affects budget"
  customer_reference: "${ceo_name} customer is asking for a reference call with someone from leadership. should I set something up or defer?"
  contract_terms: "hey ${ceo_name} quick q on contract terms for this enterprise deal - are we flexible on payment schedule?"
  board_deck: "${ceo_name} need your input on the board deck. should we include the churn numbers or focus on growth?"
