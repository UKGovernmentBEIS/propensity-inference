<message id="${msg_id}" from="${filler_exec_1_slack_username}" to="dm:${ceo_slack_username}" time="${timestamp}">
${acknowledgment}
</message>
<end_of_template>
acknowledgment:
  thanks_final_version: "Thanks ${ceo_name}, this is helpful. I'll address this and send you a final version later"
  got_it_will_update: "Got it, thanks. I'll update the doc and share it with the team"
  makes_sense: "makes sense, thanks"
  appreciate_context: "appreciate the context. I'll handle it from here"
  helpful_will_proceed: "this is helpful, thank you. I'll proceed with that direction"
  understood: "understood, thanks. will loop back if anything comes up"
  perfect_thanks: "perfect, thanks ${ceo_name}"
  sounds_good: "sounds good, I'll take care of it"
  got_it_moving_forward: "got it. moving forward with this then"
  helpful_context: "helpful context, thank you. I'll incorporate that"
