(*
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 *)

open Core

type t =
  | GetInfo
  | DisplayTypeError of string list
  | IncrementalUpdate of string list
  | Query of string
  | Stop
[@@deriving sexp, compare, hash, yojson { strict = false }]
