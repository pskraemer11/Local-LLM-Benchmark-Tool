## Befehlsoptimierung, Tokenizer bei Gemma-3 Modellen ##

# aus: "Gemma-4 Modelle - Technischer Bericht" von Google DeepMind
https://arxiv.org/pdf/2607.02770

3. Instruction Tuning (page 5)
…

**PT versus IT formatting.** 
All models share the same tokenizer, with some control tokens dedicated to IT formatting. 
A key difference is that PT models output an <eos> token at the end of generation, while IT models output <turn|> at the end of the generation. 
An example is given for IT in Table 11. 
Fine-tuning either model type thus requires adding their respective end tokens. 
We detail how to activate thinking and how models handle function calling in Table 11.


Tab. 11 (Appendix, page 17)

Tabelle 
| *Context*		        |	*Formatting*  			         |
| Thinking toggle	    |	<|think|>			             |
| Function declaration	|	<|tool>declaration:...<tool|>	 |
| Function call		    |	<|tool_call>call:...<tool_call|> |
| Thinking trace	    |	<|channel>thought ...<channel|>  |
| System turn		    |	<|turn>System			         |
| User turn		        |	<|turn>user			             |
| Model turn		    |	<|turn>model			         |
| End of turn		    |	<turn|>				             |

**Example of discussion:**
Toggle thinking mode.
Declare function.
User: I want you to book a train ticket for me.
Model: <...> Where would you like to go?
User: To Rome.
Model: <...> Looking for available tickets:
<function call>

**Model input:**
[BOS]
<|turn>system
<|think|>
<|tool>declaration:search_train{...}<tool|><turn|>
<|turn>user
I want you to book a train ticket for me.<turn|>
<|turn>model
<|channel>thought ...<channel|>Where would you like to go?<turn|>
<|turn>user
To Rome.<turn|>
<|turn>model

**Model output:**
<|channel>thought ...<channel|>Looking for available tickets:
<|tool_call>call:search_train{from:<|"|>Athens<|"|>,to:<|"|>Rome<|"|>}
<tool_call|><turn|>

Table 11 | Formatting for Gemma IT models. Explicitly add the [BOS] token after tokenization, or use
the add_bos=True option in the tokenizer. Do not tokenize the text "[BOS]". 
Add <|think|> in a leading system turn to activate the thinking mode. Check the official documentation for the function
declaration and function calling syntax, as well as more advanced examples.